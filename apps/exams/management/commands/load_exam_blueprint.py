"""Разложить структуру экзамена по базе."""

from django.core.management.base import BaseCommand

from apps.exams.blueprint import load_blueprint


class Command(BaseCommand):
    help = "Загрузить структуру ЕГЭ (задания, баллы, шкалу перевода) из кода."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Показать, что изменится, не трогая базу.",
        )
        parser.add_argument(
            "--keep-active", action="store_true",
            help="Не делать профиль активным: прогноз останется на прежнем.",
        )

    def handle(self, *args, **options):
        report = load_blueprint(
            dry_run=options["dry_run"], activate=not options["keep_active"]
        )
        self.stdout.write(
            f"{report['year']}: заданий {report['tasks']}, "
            f"максимум {report['max_primary_score']} первичных баллов, "
            f"связей с навыками добавлено {report['linked']}"
        )
        if report["tasks_without_skills"]:
            self.stdout.write(self.style.WARNING(
                "Без навыков в графе остались задания: "
                + ", ".join(map(str, report["tasks_without_skills"]))
            ))
