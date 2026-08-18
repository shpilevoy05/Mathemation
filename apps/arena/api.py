"""API арены: друзья, партии, ответы.

Всё, что влияет на результат, считает сервер: верность ответа, время и очки.
Клиент присылает только сам ответ и то, сколько он думал, — и второе
ограничивается правилом партии.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, views
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.api import get_student
from apps.accounts.models import StudentProfile

from .matchmaking import (
    bot_level_for,
    expire_stale,
    find_rival,
    get_profile,
    join_queue,
    leave_queue,
)
from .models import Friendship, Match, MatchmakingTicket, MatchQuestion
from .services import (
    accept_friend_request,
    accept_match,
    create_match,
    decline_friend_request,
    decline_match,
    friends_of,
    next_question,
    opponent_of,
    participant_for,
    rank,
    send_friend_request,
    submit_answer,
)


def _student_payload(student: StudentProfile) -> dict:
    return {
        "id": student.pk,
        "username": student.user.username,
        "name": student.user.get_full_name() or student.user.username,
    }


def _participant_payload(participant, *, reveal: bool) -> dict:
    """Состояние стороны партии.

    Пока партия идёт, чужие ответы не показываются: видно только, сколько
    вопросов соперник закрыл. Иначе арена превращается в списывание.
    """
    payload = {
        "title": participant.title,
        "is_bot": participant.is_bot,
        "answered": participant.answers.count(),
        "finished": participant.finished_at is not None,
    }
    if reveal:
        payload.update({
            "score": participant.score,
            "correct": participant.correct_count,
            "seconds": round(participant.total_time_ms / 1000, 1),
        })
    return payload


def match_review(match: Match, participant) -> list[dict]:
    """Разбор партии: что спрашивали, что ответил игрок и как правильно.

    Ошибки арены не идут в отработку — под таймером человек промахивается от
    спешки. Но не показать их вовсе значит превратить партию в бросок кубика:
    разбор и есть то, ради чего в неё стоит играть.
    """
    answers = {answer.question_id: answer for answer in participant.answers.all()}
    review = []
    for question in match.questions.select_related("assignment"):
        answer = answers.get(question.pk)
        review.append({
            "order": question.order,
            "title": question.assignment.title,
            "statement": question.assignment.statement,
            "points": question.points,
            "my_answer": answer.submitted_answer if answer else "",
            "is_correct": bool(answer and answer.is_correct),
            "answered": answer is not None,
            "correct_answer": question.assignment.correct_answer,
            "seconds": round(answer.time_ms / 1000, 1) if answer else None,
        })
    return review


def match_payload(match: Match, student) -> dict:
    me = participant_for(match, student)
    other = opponent_of(match, student)
    reveal = match.is_finished
    question = next_question(match, me) if me and not match.is_finished else None
    table = [
        {**_participant_payload(participant, reveal=True), "is_me": participant.student_id == student.pk}
        for participant in rank(match)
    ] if reveal else []
    return {
        "id": match.pk,
        "mode": match.mode,
        "mode_label": match.get_mode_display(),
        "status": match.status,
        "ege_task_number": match.ege_task_number,
        "bot_level": match.bot_level,
        "seconds_per_question": match.seconds_per_question,
        "questions_total": match.questions.count(),
        "me": _participant_payload(me, reveal=True) if me else None,
        "opponent": _participant_payload(other, reveal=reveal) if other else None,
        "results": table,
        "is_ranked": match.is_ranked,
        # Разбор появляется только после конца партии: до этого он был бы
        # списыванием у самого себя.
        "review": match_review(match, me) if (reveal and me) else [],
        "question": {
            "id": question.pk,
            "order": question.order,
            "points": question.points,
            "title": question.assignment.title,
            "statement": question.assignment.statement,
            "answer_type": question.assignment.answer_type,
        } if question else None,
    }


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
        required=False, allow_null=True, min_value=1, max_value=19
    )
    seconds_per_question = serializers.IntegerField(
        required=False, min_value=15, max_value=300, default=90
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
            )
        except DjangoValidationError as error:
            return Response({"detail": " ".join(error.messages)}, status=400)
        return Response(match_payload(match, student), status=201)


class MatchView(views.APIView):
    """GET — состояние партии для игрока."""

    def get(self, request, match_id: int):
        student = get_student(request)
        match = get_object_or_404(Match, pk=match_id, participants__student=student)
        return Response(match_payload(match, student))


class MatchAnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    answer = serializers.CharField(allow_blank=True, max_length=300)
    elapsed_ms = serializers.IntegerField(min_value=0, default=0)


class MatchAnswerView(views.APIView):
    """POST /api/arena/matches/<id>/answer/ — ответ на вопрос партии."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "attempt"

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


class QueueSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=Match.Mode.choices)
    ege_task_number = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=19
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
        try:
            ticket = join_queue(
                student,
                mode=serializer.validated_data["mode"],
                ege_task_number=serializer.validated_data.get("ege_task_number"),
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
                    student, mode=ticket.mode, ege_task_number=ticket.ege_task_number
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
        leave_queue(student)
        match = create_match(
            student,
            mode=serializer.validated_data["mode"],
            bot_level=bot_level_for(student),
            ege_task_number=serializer.validated_data.get("ege_task_number"),
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
