"""Применить предметную разметку из кода к графу знаний.

Книга методистов меняется примерно раз в год, поэтому загрузка — не фоновая
операция, а осознанный шаг при выкладке: сначала сухой прогон, чтобы увидеть
разницу, затем применение.

    python manage.py load_markup --dry-run
    python manage.py load_markup
    python manage.py load_markup --set ege13 --prune
"""

from django.core.management.base import BaseCommand, CommandError

from apps.knowledge.markup import MARKUP_SETS
from apps.knowledge.markup_loader import load_markup


class Command(BaseCommand):
    help = "Загрузить разметку навыков и связей из кода."

    def add_arguments(self, parser):
        parser.add_argument(
            "--set", dest="markup", default="",
            help="Какую разметку применить. По умолчанию — все.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Показать разницу и ничего не менять.",
        )
        parser.add_argument(
            "--prune", action="store_true",
            help="Удалить узлы, которых больше нет в книге (только свободные).",
        )

    def handle(self, *args, **options):
        names = [options["markup"]] if options["markup"] else list(MARKUP_SETS)
        unknown = [name for name in names if name not in MARKUP_SETS]
        if unknown:
            raise CommandError(
                f"Неизвестная разметка: {', '.join(unknown)}. "
                f"Доступны: {', '.join(MARKUP_SETS)}."
            )

        for name in names:
            report = load_markup(
                name, dry_run=options["dry_run"], prune=options["prune"]
            )
            for line in report.lines():
                self.stdout.write(line)
            if options["dry_run"]:
                self.stdout.write(
                    "Сухой прогон: ничего не изменено."
                    if report.has_changes
                    else "Сухой прогон: разметка уже применена."
                )
            if report.blocked_orphans and options["prune"]:
                self.stdout.write(
                    "Часть лишних узлов осталась: за них держатся задачи или "
                    "история учеников. Разберите вручную."
                )
