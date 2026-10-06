"""Демо-данные: мини-граф знаний профильной математики, уроки, задачи,
входная диагностика, пробник и четыре пользователя.

В продакшене граф и банк задач ведут методисты через админку; эта команда
нужна, чтобы сервис можно было потрогать сразу после `migrate`.
"""
from datetime import timedelta

from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import ParentProfile, StudentProfile, User
from apps.content.reference_data import seed_demo_promotion, seed_reference_data
from apps.content.models import Assignment, AssignmentSkillTag, Lesson, TheoryBlock
from apps.diagnostics.models import DiagnosticTest
from apps.expert_review.models import ExpertReviewRequest
from apps.gamification.services import generate_weekly_quests
from apps.content.theory_bank import load_theory_bank
from apps.knowledge.models import KnowledgeDependency, KnowledgeNode, TopicCluster
from apps.mocks.models import MockExam
from apps.planning.services import assign_trajectory, build_study_plan, get_active_plan

CLUSTERS = [
    # (title, exam_weight, color)
    ("Вычисления и преобразования", 1.0, "#1cb0f6"),
    ("Уравнения и неравенства", 1.4, "#58cc02"),
    ("Планиметрия", 1.0, "#ff9600"),
    ("Стереометрия", 1.1, "#ce82ff"),
    ("Вероятность и статистика", 0.8, "#ff4b4b"),
    ("Производная и исследование функций", 1.3, "#ffc800"),
    ("Векторы", 0.8, "#00c2b8"),
    ("Функции и графики", 1.0, "#a56eff"),
    ("Текстовые задачи", 1.2, "#f97316"),
    ("Числа и их свойства", 1.1, "#6b7280"),
]

# (code, title, cluster_idx, part, ege_tasks, weight, prerequisites)
# Номера заданий — по структуре 2027 года (см. apps/exams/blueprint.py).
NODES = [
    ("frac-powers", "Действия с дробями и степенями", 0, 1, [8], 1.0, []),
    ("roots-logs", "Корни и логарифмы", 0, 1, [8], 1.0, ["frac-powers"]),
    ("trig-values", "Тригонометрические выражения", 0, 1, [8], 1.0, ["frac-powers"]),
    ("linear-quadratic", "Линейные и квадратные уравнения", 1, 1, [7], 1.2, ["frac-powers"]),
    ("exp-log-eq", "Показательные и логарифмические уравнения", 1, 1, [7, 14], 1.2,
     ["roots-logs", "linear-quadratic"]),
    ("trig-eq", "Тригонометрические уравнения", 1, 2, [14], 1.3,
     ["trig-values", "linear-quadratic"]),
    ("log-ineq", "Логарифмические неравенства", 1, 2, [16], 1.3, ["exp-log-eq"]),
    ("triangles", "Треугольники и их элементы", 2, 1, [1], 1.0, []),
    ("circles", "Окружности и вписанные углы", 2, 1, [1, 18], 1.0, ["triangles"]),
    ("polyhedra", "Объёмы многогранников", 3, 1, [3], 1.0, []),
    ("plane-angles", "Угол между плоскостями", 3, 2, [15], 1.2, ["polyhedra"]),
    ("classic-prob", "Классическая вероятность", 4, 1, [4], 0.8, []),
    ("compound-prob", "Сложная вероятность", 4, 1, [5], 0.9, ["classic-prob"]),
    # Новое задание 6: случайная величина и её характеристики.
    ("random-variables", "Случайная величина: ожидание и дисперсия", 4, 1, [6], 1.0,
     ["compound-prob"]),
    ("deriv-graph", "Производная по графику", 5, 1, [9], 1.1, []),
    ("extrema", "Экстремумы и исследование функций", 5, 2, [17], 1.2, ["deriv-graph"]),
    ("parameter", "Задачи с параметром", 5, 2, [19], 1.4, ["extrema", "exp-log-eq"]),
    # Узлы ниже закрывают оставшиеся номера профиля: незамапленное задание даёт
    # нулевой вклад и занижает прогноз.
    ("vectors", "Векторы и действия с ними", 6, 1, [2], 0.9, ["triangles"]),
    ("applied-formulas", "Прикладные задачи с формулами", 7, 1, [10], 1.0,
     ["linear-quadratic"]),
    ("graph-formula", "Графики функций и их формулы", 7, 1, [12], 1.1,
     ["linear-quadratic"]),
    ("word-problems", "Текстовые задачи на движение и работу", 8, 1, [11], 1.2,
     ["linear-quadratic"]),
    # Задание 13: прежняя экономическая задача стала кратким ответом.
    ("personal-finance", "Личные и семейные финансы", 8, 1, [13], 1.2,
     ["word-problems"]),
    ("economics", "Экономическая задача", 8, 1, [13], 1.3,
     ["word-problems", "personal-finance"]),
    ("number-theory", "Числа и их свойства", 9, 2, [20], 1.2, []),
]

# (node_code, title, statement, answer, difficulty)
PART1_TASKS = [
    ("frac-powers", "Степени", "Вычислите: (2^5 · 2^-3) / 2^-2", "16", 1),
    ("frac-powers", "Дроби", "Вычислите: 3/4 + 5/8", "1.375", 1),
    ("roots-logs", "Логарифм", "Вычислите: log2(32)", "5", 1),
    ("roots-logs", "Корень", "Вычислите: √(49·4)", "14", 1),
    ("trig-values", "Синус", "Вычислите: 14·sin(π/6) + 3", "10", 2),
    ("linear-quadratic", "Квадратное уравнение",
     "Найдите меньший корень уравнения x² − 5x + 6 = 0", "2", 2),
    ("exp-log-eq", "Показательное уравнение", "Решите уравнение 2^(x−3) = 16", "7", 2),
    ("triangles", "Прямоугольный треугольник",
     "Катеты прямоугольного треугольника равны 6 и 8. Найдите гипотенузу.", "10", 1),
    ("circles", "Вписанный угол",
     "Центральный угол равен 80°. Найдите вписанный угол, опирающийся на ту же дугу.",
     "40", 2),
    ("polyhedra", "Объём куба", "Ребро куба равно 3. Найдите объём куба.", "27", 1),
    ("classic-prob", "Монета",
     "Монету бросают дважды. Найдите вероятность того, что оба раза выпадет орёл.",
     "0.25", 1),
    ("compound-prob", "Два стрелка",
     "Каждый из двух стрелков попадает с вероятностью 0.8. Найдите вероятность того, "
     "что попадут оба.", "0.64", 2),
    ("deriv-graph", "Знак производной",
     "Прямая y = 3x + 5 — касательная к графику f(x). Чему равна f'(x₀) в точке касания?",
     "3", 2),
    ("extrema", "Минимум функции", "Найдите точку минимума функции y = x² − 6x + 11", "3", 2),
    ("vectors", "Длина вектора",
     "Дан вектор a = (3; 4). Найдите его длину.", "5", 1),
    ("applied-formulas", "Формула из физики",
     "Высота h = 20 + 15t − 5t². Через сколько секунд тело окажется на высоте 30 м "
     "в первый раз?", "1", 3),
    ("graph-formula", "График параболы",
     "Парабола y = ax² + bx + c проходит через вершину (2; −1) и точку (0; 3). "
     "Найдите a.", "1", 3),
    ("word-problems", "Движение навстречу",
     "Из городов, расстояние между которыми 300 км, навстречу выехали два "
     "автомобиля со скоростями 60 и 90 км/ч. Через сколько часов они встретятся?",
     "2", 2),
    ("random-variables", "Математическое ожидание",
     "Случайная величина принимает значения 1, 2 и 5 с вероятностями 0.2, 0.5 "
     "и 0.3. Найдите её математическое ожидание.", "2.7", 3),
    ("random-variables", "Дисперсия набора",
     "Случайная величина принимает значения 0 и 10 с вероятностями 0.5 и 0.5. "
     "Найдите её дисперсию.", "25", 3),
    ("personal-finance", "Семейный бюджет",
     "Доход семьи 90 000 рублей в месяц, обязательные расходы — 65 000 рублей. "
     "Сколько месяцев нужно откладывать остаток, чтобы накопить 150 000 рублей?",
     "6", 3),
]

# (node_code, title, statement, reference_solution (по строке на шаг), max_score)
PART2_TASKS = [
    ("trig-eq", "Тригонометрическое уравнение (задача 13)",
     "а) Решите уравнение 2sin²x − sinx = 0. б) Укажите корни на отрезке [0; π].",
     "Вынеси sinx за скобку: sinx(2sinx − 1) = 0.\n"
     "Разбей на два случая: sinx = 0 и sinx = 1/2.\n"
     "Запиши серии корней и отбери попадающие в [0; π].",
     2),
    ("plane-angles", "Угол между плоскостями (задача 14)",
     "В правильной четырёхугольной пирамиде SABCD сторона основания 4, боковое ребро 6. "
     "Найдите угол между плоскостью SAB и плоскостью основания.",
     "Построй апофему боковой грани и проекцию вершины на основание.\n"
     "Искомый угол — между апофемой и её проекцией.\n"
     "Найди тангенс угла из прямоугольного треугольника.",
     3),
    ("log-ineq", "Логарифмическое неравенство (задача 15)",
     "Решите неравенство log₂(x−1) + log₂(x+1) ≤ 3.",
     "Выпиши ОДЗ: x > 1.\n"
     "Сложи логарифмы: log₂((x−1)(x+1)) ≤ 3.\n"
     "Реши x² − 1 ≤ 8 с учётом ОДЗ.",
     2),
    ("parameter", "Задача с параметром (задача 18)",
     "Найдите все значения a, при которых уравнение x² − 2ax + a² − 1 = 0 имеет два корня "
     "на интервале (−2; 4).",
     "Заметь, что левая часть — полный квадрат: (x − a)² = 1.\n"
     "Корни x = a ± 1; оба должны лежать в (−2; 4).\n"
     "Реши систему −2 < a − 1 и a + 1 < 4.",
     4),
    ("economics", "Экономическая задача (задача 16)",
     "Вклад 1 000 000 рублей открыт под 10% годовых. Каждый год после начисления "
     "процентов вкладчик снимает 200 000 рублей. Какая сумма останется на счёте "
     "через два года?",
     "Посчитай первый год: 1 000 000 · 1.1 − 200 000.\n"
     "Повтори ту же операцию для второго года.\n"
     "Проверь, что остаток положителен на каждом шаге.",
     2),
    ("number-theory", "Числа и их свойства (задача 19)",
     "а) Существует ли трёхзначное число, сумма цифр которого равна 25, кратное 9? "
     "б) Найдите наибольшее такое число, кратное 3.",
     "Вспомни признак делимости на 9: сумма цифр кратна 9.\n"
     "Сравни 25 с ближайшими кратными девяти.\n"
     "Для пункта б перебирай старшие цифры от 9 вниз.",
     4),
]

# Видео на Kinescope: в поле кладётся идентификатор ролика, embed-ссылку
# собирает модель.
DEMO_VIDEOS = {
    "frac-powers": ("demo-frac-powers", 12),
    "linear-quadratic": ("demo-linear-quadratic", 18),
}

DEMO_EDGE_THRESHOLDS = {
    ("roots-logs", "frac-powers"): 50,
    ("linear-quadratic", "frac-powers"): 80,
}


class Command(BaseCommand):
    help = "Наполняет базу демо-данными (идемпотентно)."

    @transaction.atomic
    def handle(self, *args, **options):
        clusters = []
        for order, (title, weight, color) in enumerate(CLUSTERS):
            cluster, _ = TopicCluster.objects.update_or_create(
                title=title,
                defaults={"exam_weight": weight, "order": order, "color": color},
            )
            clusters.append(cluster)

        nodes: dict[str, KnowledgeNode] = {}
        for order, (code, title, ci, part, tasks, weight, _) in enumerate(NODES):
            nodes[code], _ = KnowledgeNode.objects.update_or_create(
                code=code,
                defaults={
                    "title": title, "cluster": clusters[ci], "weight": weight,
                    "exam_part": part, "ege_task_numbers": tasks, "order": order,
                },
            )
        for code, _, _, _, _, _, prereqs in NODES:
            for pre in prereqs:
                KnowledgeDependency.objects.update_or_create(
                    node=nodes[code],
                    prerequisite=nodes[pre],
                    defaults={"min_mastery": DEMO_EDGE_THRESHOLDS.get((code, pre), 70)},
                )

        for code, node in nodes.items():
            lesson, _ = Lesson.objects.update_or_create(
                node=node, title=f"Урок: {node.title}",
                defaults={
                    "order": node.order,
                    # Демо-контент готов, поэтому уроки сразу опубликованы:
                    # черновик ученику не показывается.
                    "status": Lesson.Status.PUBLISHED,
                    "published_at": timezone.now(),
                },
            )
            if code in DEMO_VIDEOS:
                lesson.video_url, lesson.video_duration_minutes = DEMO_VIDEOS[code]
                lesson.save(update_fields=["video_url", "video_duration_minutes"])
            TheoryBlock.objects.update_or_create(
                lesson=lesson, order=0,
                defaults={
                    "title": "Коротко о главном",
                    "body": f"Ключевые факты и приёмы по теме «{node.title}» "
                            f"(задания ЕГЭ №{', '.join(map(str, node.ege_task_numbers))}).",
                },
            )

        part1 = []
        for code, title, statement, answer, diff in PART1_TASKS:
            node = nodes[code]
            a, _ = Assignment.objects.update_or_create(
                title=title,
                defaults={
                    "lesson": node.lessons.first(), "statement": statement,
                    "correct_answer": answer, "exam_part": Assignment.Part.PART1,
                    "difficulty": diff, "max_score": 1,
                },
            )
            AssignmentSkillTag.objects.get_or_create(assignment=a, node=node)
            part1.append(a)

        part2 = []
        for code, title, statement, solution, max_score in PART2_TASKS:
            node = nodes[code]
            a, _ = Assignment.objects.update_or_create(
                title=title,
                defaults={
                    "lesson": node.lessons.first(), "statement": statement,
                    "reference_solution": solution, "exam_part": Assignment.Part.PART2,
                    "difficulty": 4, "max_score": max_score,
                },
            )
            AssignmentSkillTag.objects.get_or_create(assignment=a, node=node)
            part2.append(a)

        diagnostic, _ = DiagnosticTest.objects.update_or_create(
            title="Входная диагностика (короткий срез по ключевым узлам)"
        )
        diagnostic.assignments.set(part1)

        full_mock, _ = DiagnosticTest.objects.update_or_create(
            title="Входной полный пробник"
        )
        full_mock.assignments.set(part1 + part2)

        mock, _ = MockExam.objects.update_or_create(
            title="Пробник ЕГЭ №1", defaults={"duration_minutes": 235}
        )
        mock.assignments.set(part1 + part2)

        profile, _reference_report = seed_reference_data(nodes=nodes)
        seed_demo_promotion()

        student_user, created = User.objects.get_or_create(
            username="student", defaults={"role": User.Role.STUDENT}
        )
        if created:
            student_user.set_password("demo12345")
            student_user.save()
        student, _ = StudentProfile.objects.get_or_create(
            user=student_user,
            defaults={
                "target_score": 84, "weekly_hours": 8,
                "exam_date": timezone.localdate() + timedelta(days=180),
            },
        )
        assign_trajectory(student, student.target_score)
        if get_active_plan(student) is None:
            build_study_plan(student, reason="seed_demo")
        generate_weekly_quests(student)

        parent_user, created = User.objects.get_or_create(
            username="parent", defaults={"role": User.Role.PARENT}
        )
        if created:
            parent_user.set_password("demo12345")
            parent_user.save()
        parent, _ = ParentProfile.objects.get_or_create(user=parent_user)
        parent.children.add(student)

        expert_user, created = User.objects.get_or_create(
            username="expert",
            defaults={"role": User.Role.EXPERT, "is_staff": True},
        )
        if created:
            expert_user.set_password("demo12345")
        expert_user.role = User.Role.EXPERT
        expert_user.is_staff = True
        expert_user.save()
        expert_user.groups.add(Group.objects.get(name="Эксперты"))

        methodist_user, created = User.objects.get_or_create(
            username="methodist",
            defaults={"role": User.Role.METHODIST, "is_staff": True},
        )
        if created:
            methodist_user.set_password("demo12345")
        methodist_user.role = User.Role.METHODIST
        methodist_user.is_staff = True
        methodist_user.save()
        methodist_user.groups.add(Group.objects.get(name="Методисты"))

        smm_user, created = User.objects.get_or_create(
            username="smm",
            defaults={"role": User.Role.SMM, "is_staff": True},
        )
        if created:
            smm_user.set_password("demo12345")
        smm_user.role = User.Role.SMM
        smm_user.is_staff = True
        smm_user.save()
        smm_user.groups.add(Group.objects.get(name="SMM"))

        ExpertReviewRequest.objects.get_or_create(
            student=student,
            assignment=part2[0],
            status=ExpertReviewRequest.Status.SUBMITTED,
            defaults={
                "solution_file": ContentFile(
                    b"Mathemation demo solution scan",
                    name="demo-part2-solution.txt",
                )
            },
        )

        self._seed_engagement(nodes, part1, student)
        # Банк теории живёт разметкой в коде: демо-данные его просто раскладывают.
        theory = load_theory_bank()

        if options.get("verbosity", 1) < 1:
            return
        self.stdout.write(self.style.SUCCESS(
            f"Демо-данные готовы: {KnowledgeNode.objects.count()} узлов, "
            f"{Assignment.objects.count()} задач, "
            f"{theory['created'] + theory['updated']} вопросов по теории, "
            f"профиль экзамена {profile.year} "
            f"({profile.tasks.count()} заданий). "
            "Пользователи: student / parent / expert / methodist / smm "
            "(пароль demo12345)."
        ))

    def _seed_engagement(self, nodes, part1, student):
        """Демонстрационные домашка и задание дня.

        Без них кабинет ученика выглядит пустым, и пройти сценарии роли
        (в том числе по docs/test_launch.md) нельзя.
        """
        from apps.content.models import DailyChallenge, Homework
        from apps.content.services import assign_homework
        homework, _ = Homework.objects.get_or_create(
            title="Домашка: вычисления и уравнения",
            defaults={
                "lesson": nodes["frac-powers"].lessons.first(),
                "description": "Три задачи на разогрев перед новой темой.",
                "status": Homework.Status.PUBLISHED,
                "due_at": timezone.now() + timedelta(days=7),
            },
        )
        for order, assignment in enumerate(part1[:3]):
            homework.tasks.get_or_create(assignment=assignment, defaults={"order": order})
        assign_homework(homework, [student])

        DailyChallenge.objects.update_or_create(
            date=timezone.localdate(),
            defaults={
                "assignment": part1[0],
                "title": "Разминка дня",
                "reward_xp": 15,
                "is_active": True,
            },
        )
        # Витрину раскладывает общий каталог: коды косметики совпадают с
        # именами файлов дизайна, а расходники — те же, что выдаёт лига.
        from apps.accounts.models import StudentProfile
        from apps.economy.catalog import grant_base_avatars, load_cosmetics

        load_cosmetics()
        # Базовые аватары есть у каждого ученика с первой минуты.
        for profile in StudentProfile.objects.all():
            grant_base_avatars(profile)
