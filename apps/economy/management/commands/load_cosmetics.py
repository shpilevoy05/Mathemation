"""Разложить каталог косметики по витрине."""

from django.core.management.base import BaseCommand

from apps.economy.catalog import load_cosmetics


class Command(BaseCommand):
    help = "Загрузить каталог аватаров, рамок и тем (идемпотентно)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        report = load_cosmetics(dry_run=options["dry_run"])
        self.stdout.write(
            f"создано {report['created']}, обновлено {report['updated']}"
        )
