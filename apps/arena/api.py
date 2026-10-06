"""API арены: друзья, партии, ходы во всех трёх режимах.

Всё, что влияет на результат, считает сервер: верность ответа, время, очки и
то, чей сейчас ход. Клиент присылает только выбранный вариант или текст ответа.

Состояние партии приходит одним объектом — им же рисуется страница при первой
загрузке и обновляется при опросе. Один формат вместо двух: расхождение между
«как отрисовалось» и «как обновилось» — самый частый источник призрачных
ошибок в живых экранах.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, views
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.api import get_student
from apps.accounts.models import StudentProfile
from apps.economy.services import cosmetic_codes

from .ranks import rank_for_rating
from .matchmaking import (
    bot_level_for,
    expire_stale,
    find_rival,
    get_profile,
    join_queue,
    leave_queue,
    profiles_by_student_id,
)
from .models import ArenaProfile, Friendship, Match, MatchmakingTicket, MatchQuestion
from .services import (
    LOBBY_TTL_SECONDS,
    accept_friend_request,
    accept_match,
    advance,
    cancel_match,
    create_match,
    decline_friend_request,
    decline_match,
    friends_of,
    join_match,
    leave_match,
    next_question,
    note_presence,
    open_cell,
    open_question,
    opponent_of,
    participant_for,
    pick_cell,
    rank,
    send_friend_request,
    submit_answer,
    submit_board_answer,
    submit_quiz_answer,
)


def _student_payload(student: StudentProfile) -> dict:
    return {
        "id": student.pk,
        "username": student.user.username,
        "name": student.user.get_full_name() or student.user.username,
    }


def _participant_payload(participant, *, reveal: bool, profile_map=None) -> dict:
    """Карточка стороны: имя, оформление и счёт.

    Счёт соперника виден всё время, во всех режимах: это табло, а не подсказка.
    Скрыты остаются только сами ответы — иначе арена превращается в списывание.
    """
    codes = (
        cosmetic_codes(participant.student)
        if participant.student_id
        else {"avatar": "", "frame": ""}
    )
    title = participant.title
    payload = {
        "id": participant.pk,
        "title": title,
        "letter": title[:1].upper(),
        "is_bot": participant.is_bot,
        "avatar": codes["avatar"],
        "frame": codes["frame"],
        "score": participant.score,
        "correct": participant.correct_count,
        "answered": participant.answers.count(),
        "finished": participant.finished_at is not None,
        "seconds": round(participant.total_time_ms / 1000, 1) if reveal else None,
    }
    if not participant.is_bot and participant.student_id is not None:
        profile = (profile_map or {}).get(participant.student_id)
        payload["rank_code"] = rank_for_rating(
            profile.rating if profile else ArenaProfile.BASE_RATING
        )["code"]
    return payload


def match_review(match: Match, participant) -> list[dict]:
    """Разбор партии: что спрашивали, что ответил игрок и как правильно.

    Ошибки арены не идут в отработку — под таймером человек промахивается от
    спешки. Но не показать их вовсе значит превратить партию в бросок кубика:
    разбор и есть то, ради чего в неё стоит играть.
    """
    answers = {answer.question_id: answer for answer in participant.answers.all()}
    review = []
    for question in match.questions.select_related("assignment", "theory", "resolved_by"):
        answer = answers.get(question.pk)
        review.append({
            "order": question.order,
            "title": question.topic_title or question.title,
            "statement": question.prompt,
            "points": question.points,
            "my_answer": answer.submitted_answer if answer else "",
            "is_correct": bool(answer and answer.is_correct),
            "answered": answer is not None,
            "correct_answer": question.correct_answer,
            "seconds": round(answer.time_ms / 1000, 1) if answer else None,
            "points_delta": answer.points_delta if answer else 0,
            # Кто в итоге забрал вопрос: в квизе и «своей игре» его мог взять
            # соперник, пока игрок думал.
            "taken_by": question.resolved_by.title if question.resolved_by_id else "",
        })
    return review


def _lobby_payload(match: Match, student, me) -> dict:
    """Кого ждём и сколько уже ждём.

    Экран ожидания — не украшение: без него игрок видит пустую доску и решает,
    что партия сломалась.
    """
    from django.utils import timezone

    # В списке — только соперники: себя в «кого ждём» видеть незачем, за столом
    # игрок оказывается в тот момент, когда открыл экран.
    waiting = [
        participant.title
        for participant in match.participants.select_related("student__user")
        if participant.joined_at is None and participant.student_id != student.pk
    ]
    waited = int((timezone.now() - match.created_at).total_seconds())
    return {
        "waiting_for": waiting,
        "invited": match.status == Match.Status.INVITED,
        "joined": me is not None and me.joined_at is not None,
        "seconds_waiting": waited,
        "seconds_left": max(0, LOBBY_TTL_SECONDS - waited),
        # Отменяет тот, кто позвал: остальным отказываться, а не отменять.
        "can_cancel": match.created_by_id == student.pk,
    }


def _seconds_left(match: Match, participant) -> int | None:
    """Сколько секунд осталось лично игроку в режиме «на время»."""
    from django.utils import timezone

    if match.limit_kind != Match.Limit.TIME or participant is None:
        return None
    if participant.started_at is None:
        return match.time_limit_seconds
    spent = (timezone.now() - participant.started_at).total_seconds()
    return max(0, int(round(match.time_limit_seconds - spent)))


def _question_payload(question) -> dict:
    return {
        "id": question.pk,
        "order": question.order,
        "points": question.points,
        "title": question.topic_title or question.title,
        "statement": question.prompt,
        "answer_type": (
            question.assignment.answer_type if question.assignment_id else "short"
        ),
    }


def _time_left(match: Match, question) -> int:
    from django.utils import timezone

    if question.opened_at is None:
        return match.seconds_per_question
    spent = (timezone.now() - question.opened_at).total_seconds()
    return max(0, int(round(match.seconds_per_question - spent)))


def _quiz_payload(match: Match, me) -> dict:
    """Общий вопрос квиза: у обоих игроков он один и тот же."""
    question = open_question(match)
    total = match.questions.count()
    played = match.questions.filter(resolved_at__isnull=False).count()
    if question is None or question.opened_at is None:
        return {"question": None, "played": played, "total": total}
    my_answer = (
        me.answers.filter(question=question).first() if me is not None else None
    )
    return {
        "question": {
            "id": question.pk,
            "order": question.order,
            "topic": question.topic_title,
            "prompt": question.prompt,
            "options": list(question.options or []),
            "points": question.points,
            "seconds_left": _time_left(match, question),
            "hint": question.theory.hint if question.theory_id else "",
        },
        # Промахнувшийся ждёт: второй попытки на том же вопросе нет.
        "locked": my_answer is not None,
        "my_choice": my_answer.chosen_option if my_answer else None,
        "played": played,
        "total": total,
    }


def _board_answers(cell, me) -> list[dict]:
    """Кто и что ответил на клетку.

    В «своей игре» ответы не секрет: вопрос общий, звучит вслух и уже сыгран.
    Видеть, что сказал соперник, — половина смысла игры.
    """
    return [
        {
            "title": answer.participant.title,
            "is_me": me is not None and answer.participant_id == me.pk,
            "answer": answer.submitted_answer,
            "is_correct": answer.is_correct,
            "points_delta": answer.points_delta,
        }
        for answer in cell.answers.select_related("participant__student__user")
    ]


def _rebound_note(cell, wrong_answer, answering) -> str:
    """Фраза о перехвате: кто ошибся, что сказал и к кому ушла клетка.

    Собирается на сервере, а не в двух местах интерфейса: страница и опрос
    рисуют один и тот же текст, и разойтись им негде.
    """
    if cell.rebound_by_id is None:
        return ""
    who = "Вы" if (wrong_answer and wrong_answer["is_me"]) else (
        wrong_answer["title"] if wrong_answer else "Соперник"
    )
    said = f" «{wrong_answer['answer']}»" if wrong_answer and wrong_answer["answer"] else ""
    verb = "ответили" if who == "Вы" else "ответил"
    target = answering.title if answering else "сопернику"
    return f"{who} {verb}{said} — неверно. Клетка перешла к {target}: полминуты на ответ."


def _board_payload(match: Match, me) -> dict:
    """Доска «своей игры»: клетки по темам и цене плюс открытый вопрос."""
    cells = list(
        match.questions.select_related(
            "theory", "resolved_by", "picked_by", "rebound_by"
        ).prefetch_related("answers__participant__student__user")
    )
    active = open_cell(match)
    columns: dict[int, dict] = {}
    for cell in cells:
        column = columns.setdefault(
            cell.column, {"title": cell.topic_title, "cells": []}
        )
        if active is not None and cell.pk == active.pk:
            state = "active"
        elif cell.resolved_at is None:
            state = "free"
        elif cell.resolved_by_id is None:
            state = "burned"
        elif me is not None and cell.resolved_by_id == me.pk:
            state = "mine"
        else:
            state = "rival"
        column["cells"].append({
            "id": cell.pk,
            "points": cell.points,
            "state": state,
        })
    turn = match.turn_participant
    payload = {
        "columns": [columns[key] for key in sorted(columns)],
        "turn": (
            None if turn is None else ("me" if me is not None and turn.pk == me.pk else "rival")
        ),
        "turn_title": turn.title if turn is not None else "",
        "open": None,
    }
    if active is not None:
        answering = active.rebound_by or active.picked_by
        # На перехваченной клетке ответ ровно один — тот, из-за которого она
        # и перешла. Чей он, видно по `is_me`.
        wrong_answer = next(iter(_board_answers(active, me)), None)
        payload["open"] = {
            "id": active.pk,
            "topic": active.topic_title,
            "prompt": active.prompt,
            "points": active.points,
            "seconds_left": _time_left(match, active),
            "hint": active.theory.hint if active.theory_id else "",
            "mine": me is not None and active.answering_id == me.pk,
            "picked_by": active.picked_by.title if active.picked_by_id else "",
            "answering": answering.title if answering else "",
            # Перехват: первый ошибся, и клетка досталась сопернику вместе с
            # его ответом — как в телеигре, где ошибку слышат все.
            "rebound": active.rebound_by_id is not None,
            "wrong_answer": wrong_answer,
            "rebound_note": _rebound_note(active, wrong_answer, answering),
        }
    # Журнал: чем кончились разыгранные клетки и что отвечал соперник.
    payload["log"] = [
        {
            "points": cell.points,
            "topic": cell.topic_title,
            "correct_answer": cell.correct_answer,
            "taken_by": cell.resolved_by.title if cell.resolved_by_id else "",
            "answers": _board_answers(cell, me),
        }
        for cell in sorted(
            (cell for cell in cells if cell.resolved_at is not None),
            key=lambda cell: cell.resolved_at, reverse=True,
        )[:6]
    ]
    return payload


def match_payload(match: Match, student) -> dict:
    """Состояние партии глазами игрока.

    Время двигается здесь же: у партии нет отдельного «часовщика», поэтому
    каждое обращение сначала доигрывает её до текущего момента — закрывает
    просроченные вопросы и даёт боту сходить по своему расписанию.
    """
    advance(match)
    match.refresh_from_db()
    participants = list(
        match.participants.select_related("student__user").prefetch_related("answers")
    )
    me = next((row for row in participants if row.student_id == student.pk), None)
    other = next((row for row in participants if row.student_id != student.pk), None)
    profile_map = profiles_by_student_id(
        row.student for row in participants if row.student_id is not None
    )
    reveal = match.is_finished
    table = [
        {**_participant_payload(participant, reveal=True, profile_map=profile_map), "is_me": participant.student_id == student.pk}
        for participant in rank(match)
    ] if reveal else []
    payload = {
        "id": match.pk,
        "mode": match.mode,
        "mode_label": match.get_mode_display(),
        "status": match.status,
        "ege_task_number": match.ege_task_number,
        "bot_level": match.bot_level,
        "seconds_per_question": match.seconds_per_question,
        "limit_kind": match.limit_kind,
        "time_limit_seconds": match.time_limit_seconds,
        "seconds_left": _seconds_left(match, me),
        "questions_total": match.questions.count(),
        "me": _participant_payload(me, reveal=True, profile_map=profile_map) if me else None,
        "opponent": _participant_payload(other, reveal=reveal, profile_map=profile_map) if other else None,
        "results": table,
        "is_ranked": match.is_ranked,
        "revision": match.revision,
        "lobby": _lobby_payload(match, student, me) if match.is_waiting else None,
        # Разбор появляется только после конца партии: до этого он был бы
        # списыванием у самого себя.
        "review": match_review(match, me) if (reveal and me) else [],
        "question": None,
        "quiz": None,
        "board": None,
    }
    if match.is_waiting:
        return payload
    if match.mode == Match.Mode.QUIZ:
        payload["quiz"] = _quiz_payload(match, me)
    elif match.mode == Match.Mode.BOARD:
        payload["board"] = _board_payload(match, me)
    else:
        question = next_question(match, me) if me and not match.is_finished else None
        payload["question"] = _question_payload(question) if question else None
    return payload


class FriendListView(views.APIView):
    """GET — друзья, входящие и исходящие заявки."""

    def get(self, request):
        student = get_student(request)
        incoming = Friendship.objects.filter(
            to_student=student, status=Friendship.Status.PENDING
        ).select_related("from_student__user")
        outgoing = Friendship.objects.filter(
            from_student=student, status=Friendship.Status.PENDING
        ).select_related("to_student__user")
        return Response({
            "friends": [_student_payload(friend) for friend in friends_of(student)],
            "incoming": [
                {"id": link.pk, **_student_payload(link.from_student)} for link in incoming
            ],
            "outgoing": [
                {"id": link.pk, **_student_payload(link.to_student)} for link in outgoing
            ],
        })


class FriendRequestSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)


class FriendRequestView(views.APIView):
    """POST {"username": "..."} — позвать в друзья."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "purchase"

    def post(self, request):
        student = get_student(request)
        serializer = FriendRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        other = StudentProfile.objects.filter(
            user__username__iexact=serializer.validated_data["username"].strip()
        ).select_related("user").first()
        if other is None:
            # Один и тот же ответ на «нет такого» и «это не ученик»: перебор
            # логинов не должен превращаться в поиск по базе.
            return Response({"detail": "Такого ученика нет."}, status=404)
        try:
            link = send_friend_request(student, other)
        except DjangoValidationError as error:
            return Response({"detail": " ".join(error.messages)}, status=400)
        return Response({"id": link.pk, "status": link.status}, status=201)


class FriendAnswerView(views.APIView):
    """POST /api/arena/friends/<id>/(accept|decline)/ — ответ на заявку."""

    def post(self, request, link_id: int, action: str):
        student = get_student(request)
        link = get_object_or_404(Friendship, pk=link_id)
        handler = accept_friend_request if action == "accept" else decline_friend_request
        try:
            handler(link, student)
        except DjangoValidationError as error:
            return Response({"detail": " ".join(error.messages)}, status=403)
        return Response({"id": link.pk, "status": link.status})


class CreateMatchSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=Match.Mode.choices)
    opponent_id = serializers.IntegerField(required=False, allow_null=True)
    bot_level = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=5)
    ege_task_number = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=20
    )
    seconds_per_question = serializers.IntegerField(
        required=False, min_value=15, max_value=300, default=90
    )
    limit_kind = serializers.ChoiceField(
        choices=Match.Limit.choices, required=False, default=Match.Limit.QUESTIONS
    )
    time_limit_seconds = serializers.IntegerField(
        required=False, allow_null=True, min_value=60, max_value=900
    )
    question_count = serializers.IntegerField(
        required=False, allow_null=True, min_value=4, max_value=20
    )


class CreateMatchView(views.APIView):
    """POST /api/arena/matches/ — создать партию с другом или ботом."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "purchase"

    def post(self, request):
        student = get_student(request)
        serializer = CreateMatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        opponent = None
        if data.get("opponent_id"):
            opponent = get_object_or_404(StudentProfile, pk=data["opponent_id"])
        try:
            match = create_match(
                student,
                mode=data["mode"],
                opponent=opponent,
                bot_level=data.get("bot_level"),
                ege_task_number=data.get("ege_task_number"),
                seconds_per_question=data.get("seconds_per_question", 90),
                limit_kind=data.get("limit_kind", Match.Limit.QUESTIONS),
                time_limit_seconds=data.get("time_limit_seconds"),
                question_count=data.get("question_count"),
            )
        except DjangoValidationError as error:
            return Response({"detail": " ".join(error.messages)}, status=400)
        return Response(match_payload(match, student), status=201)


class MatchView(views.APIView):
    """GET — состояние партии для игрока.

    Экран опрашивает партию каждые несколько секунд, и почти всегда новостей
    нет. Поэтому ответ помечен ETag с номером состояния: если у клиента тот же
    номер, возвращается 304 без сборки состояния — это разница между парой
    запросов в базу и двумя десятками.
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "arena_state"

    def get(self, request, match_id: int):
        student = get_student(request)
        match = get_object_or_404(Match, pk=match_id, participants__student=student)
        # Экран сам говорит «я здесь»: по этой отметке партия понимает, что
        # игрок не закрыл вкладку. Отметка живёт в кеше и в базу не пишется.
        note_presence(match, student)
        # Сначала двигаем время: иначе клиент получит «изменений нет» там, где
        # у вопроса как раз истёк таймер.
        advance(match)
        match.refresh_from_db(fields=["revision", "status"])
        tag = f'W/"{match.pk}-{match.revision}"'
        if request.headers.get("If-None-Match") == tag:
            response = Response(status=304)
            response["ETag"] = tag
            return response
        response = Response(match_payload(match, student))
        response["ETag"] = f'W/"{match.pk}-{match.revision}"'
        return response


class MatchJoinView(views.APIView):
    """POST — «я за столом». Партия начинается, когда зашли все.

    Личные часы режима «на время» тоже стартуют здесь: отсчёт идёт с момента,
    когда игрок оказался в начавшейся партии, а не с её создания.
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "arena_state"

    def post(self, request, match_id: int):
        student = get_student(request)
        match = get_object_or_404(Match, pk=match_id, participants__student=student)
        join_match(match, student)
        match.refresh_from_db()
        note_presence(match, student)
        return Response(match_payload(match, student))


class MatchLeaveView(views.APIView):
    """POST — выйти из партии. Победа достаётся оставшемуся."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "arena_move"

    def post(self, request, match_id: int):
        student = get_student(request)
        match = get_object_or_404(Match, pk=match_id, participants__student=student)
        try:
            leave_match(match, student)
        except DjangoValidationError as error:
            return Response({"detail": " ".join(error.messages)}, status=409)
        match.refresh_from_db()
        return Response(match_payload(match, student))


class MatchCancelView(views.APIView):
    """POST — снять партию, которая так и не началась."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "arena_move"

    def post(self, request, match_id: int):
        student = get_student(request)
        match = get_object_or_404(Match, pk=match_id, participants__student=student)
        try:
            cancel_match(match, student)
        except DjangoValidationError as error:
            return Response({"detail": " ".join(error.messages)}, status=409)
        return Response(match_payload(match, student))


class MatchAnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    answer = serializers.CharField(allow_blank=True, max_length=300)
    elapsed_ms = serializers.IntegerField(min_value=0, default=0)


class MatchAnswerView(views.APIView):
    """POST /api/arena/matches/<id>/answer/ — ответ в нарешивании."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "arena_move"

    def post(self, request, match_id: int):
        student = get_student(request)
        match = get_object_or_404(Match, pk=match_id, participants__student=student)
        serializer = MatchAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = get_object_or_404(
            MatchQuestion, pk=serializer.validated_data["question_id"], match=match
        )
        try:
            answer = submit_answer(
                match, student, question,
                serializer.validated_data["answer"],
                serializer.validated_data["elapsed_ms"],
            )
        except DjangoValidationError as error:
            return Response({"detail": " ".join(error.messages)}, status=409)
        match.refresh_from_db()
        payload = match_payload(match, student)
        payload["last_answer"] = {"is_correct": answer.is_correct}
        return Response(payload)


class QuizAnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    option = serializers.IntegerField(min_value=0, max_value=3)


class QuizAnswerView(views.APIView):
    """POST /api/arena/matches/<id>/quiz/ — нажать вариант в квизе.

    Отказ (409) здесь — нормальный ход игры: вопрос мог забрать соперник, пока
    летел запрос. Интерфейс на такой ответ просто перерисовывает состояние.
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "arena_move"

    def post(self, request, match_id: int):
        student = get_student(request)
        match = get_object_or_404(Match, pk=match_id, participants__student=student)
        serializer = QuizAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = get_object_or_404(
            MatchQuestion, pk=serializer.validated_data["question_id"], match=match
        )
        try:
            answer = submit_quiz_answer(
                match, student, question, serializer.validated_data["option"]
            )
        except DjangoValidationError as error:
            match.refresh_from_db()
            payload = match_payload(match, student)
            payload["detail"] = " ".join(error.messages)
            return Response(payload, status=409)
        match.refresh_from_db()
        payload = match_payload(match, student)
        payload["last_answer"] = {"is_correct": answer.is_correct}
        return Response(payload)


class PickCellSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()


class PickCellView(views.APIView):
    """POST /api/arena/matches/<id>/pick/ — выбрать клетку в «своей игре»."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "arena_move"

    def post(self, request, match_id: int):
        student = get_student(request)
        match = get_object_or_404(Match, pk=match_id, participants__student=student)
        serializer = PickCellSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = get_object_or_404(
            MatchQuestion, pk=serializer.validated_data["question_id"], match=match
        )
        try:
            pick_cell(match, student, question)
        except DjangoValidationError as error:
            match.refresh_from_db()
            payload = match_payload(match, student)
            payload["detail"] = " ".join(error.messages)
            return Response(payload, status=409)
        match.refresh_from_db()
        return Response(match_payload(match, student))


class BoardAnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    answer = serializers.CharField(allow_blank=True, max_length=300)


class BoardAnswerView(views.APIView):
    """POST /api/arena/matches/<id>/board/ — ответ на открытую клетку."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "arena_move"

    def post(self, request, match_id: int):
        student = get_student(request)
        match = get_object_or_404(Match, pk=match_id, participants__student=student)
        serializer = BoardAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = get_object_or_404(
            MatchQuestion, pk=serializer.validated_data["question_id"], match=match
        )
        try:
            answer = submit_board_answer(
                match, student, question, serializer.validated_data["answer"]
            )
        except DjangoValidationError as error:
            match.refresh_from_db()
            payload = match_payload(match, student)
            payload["detail"] = " ".join(error.messages)
            return Response(payload, status=409)
        match.refresh_from_db()
        payload = match_payload(match, student)
        payload["last_answer"] = {
            "is_correct": answer.is_correct,
            "points_delta": answer.points_delta,
        }
        return Response(payload)


class QueueSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=Match.Mode.choices)
    ege_task_number = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=20
    )
    limit_kind = serializers.ChoiceField(
        choices=Match.Limit.choices, required=False, default=Match.Limit.QUESTIONS
    )
    time_limit_seconds = serializers.IntegerField(
        required=False, allow_null=True, min_value=60, max_value=900
    )
    question_count = serializers.IntegerField(
        required=False, allow_null=True, min_value=4, max_value=20
    )
    bot_level = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=5
    )


def _ticket_payload(ticket, student) -> dict:
    from .matchmaking import get_profile, window_for

    payload = {
        "status": ticket.status,
        "rating": get_profile(student).rating,
        "search_window": window_for(ticket),
        "match_id": ticket.match_id,
    }
    if ticket.match_id:
        payload["match_url"] = f"/arena/match/{ticket.match_id}/"
    return payload


class QueueView(views.APIView):
    """POST — встать в очередь на случайного соперника, GET — проверить статус."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "purchase"

    def post(self, request):
        student = get_student(request)
        serializer = QueueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            ticket = join_queue(
                student,
                mode=data["mode"],
                ege_task_number=data.get("ege_task_number"),
                limit_kind=data.get("limit_kind", Match.Limit.QUESTIONS),
                time_limit_seconds=data.get("time_limit_seconds") or 0,
                question_count=data.get("question_count") or 0,
            )
        except DjangoValidationError as error:
            return Response({"detail": " ".join(error.messages)}, status=400)
        return Response(_ticket_payload(ticket, student), status=201)

    def get(self, request):
        student = get_student(request)
        expire_stale()
        ticket = (
            MatchmakingTicket.objects.filter(student=student)
            .exclude(status=MatchmakingTicket.Status.CANCELLED)
            .order_by("-created_at")
            .first()
        )
        if ticket is None:
            return Response({"status": "idle", "rating": get_profile(student).rating})
        if ticket.status == MatchmakingTicket.Status.WAITING:
            # Пока игрок ждёт, очередь могла пополниться: пробуем свести снова.
            rival = find_rival(ticket)
            if rival is not None:
                ticket = join_queue(
                    student, mode=ticket.mode, ege_task_number=ticket.ege_task_number,
                    limit_kind=ticket.limit_kind,
                    time_limit_seconds=ticket.time_limit_seconds,
                    question_count=ticket.question_count,
                )
        return Response(_ticket_payload(ticket, student))

    def delete(self, request):
        student = get_student(request)
        leave_queue(student)
        return Response({"status": "idle", "rating": get_profile(student).rating})


class BotFallbackView(views.APIView):
    """POST — сыграть с ботом своего уровня, если живого соперника нет."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "purchase"

    def post(self, request):
        student = get_student(request)
        serializer = QueueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        leave_queue(student)
        match = create_match(
            student,
            mode=data["mode"],
            # Уровень выбирает игрок; если не выбрал — берём равный ему по
            # рейтингу: запасной бот должен быть соперником, а не наказанием.
            bot_level=data.get("bot_level") or bot_level_for(student),
            ege_task_number=data.get("ege_task_number"),
            limit_kind=data.get("limit_kind", Match.Limit.QUESTIONS),
            time_limit_seconds=data.get("time_limit_seconds") or 0,
            question_count=data.get("question_count") or 0,
        )
        return Response(match_payload(match, student), status=201)


class MatchInviteView(views.APIView):
    """POST /api/arena/matches/<id>/(accept|decline)/ — ответ на вызов друга."""

    def post(self, request, match_id: int, action: str):
        student = get_student(request)
        match = get_object_or_404(Match, pk=match_id, participants__student=student)
        handler = accept_match if action == "accept" else decline_match
        try:
            handler(match, student)
        except DjangoValidationError as error:
            return Response({"detail": " ".join(error.messages)}, status=403)
        return Response(match_payload(match, student))
