"""Разложить банк теоретических вопросов арены по базе."""

from django.core.management.base import BaseCommand

from apps.content.theory_bank import load_theory_bank


class Command(BaseCommand):
    help = "Загрузить банк вопросов по теории для арены (идемпотентно)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Показать, что изменится, не трогая базу.",
        )

    def handle(self, *args, **options):
        report = load_theory_bank(dry_run=options["dry_run"])
        self.stdout.write(
            f"создано {report['created']}, обновлено {report['updated']}, "
            f"пропущено (нет темы) {report['skipped']}"
        )
