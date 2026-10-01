"""Production bootstrap without demo users or learning activity."""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.content.reference_data import seed_reference_data
from apps.knowledge.markup import MARKUP_SETS
from apps.knowledge.markup_loader import load_markup


class Command(BaseCommand):
    help = "Создаёт production-справочники без демонстрационных данных."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать, что будет создано, и откатить изменения.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        self.stdout.write("Разметка графа знаний:")
        for name in MARKUP_SETS:
            markup_report = load_markup(name, dry_run=False, prune=False)
            for line in markup_report.lines():
                self.stdout.write(line)

        _profile, report = seed_reference_data()
        if report.created:
            self.stdout.write("Будут созданы:" if dry_run else "Созданы:")
            for label in report.created:
                self.stdout.write(f"- {label}")
        else:
            self.stdout.write("Новых справочников нет.")

        if dry_run:
            transaction.set_rollback(True)
            self.stdout.write("Сухой прогон: изменения не сохранены.")
        else:
            self.stdout.write(self.style.SUCCESS("Production-справочники готовы."))
