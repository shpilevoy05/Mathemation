"""Собрать спрайт косметики из дизайн-исходников."""

from django.core.management.base import BaseCommand

from apps.economy.sprite import write_sprite


class Command(BaseCommand):
    help = "Собрать static/img/cosmetics.svg из design/svg/."

    def handle(self, *args, **options):
        report = write_sprite()
        self.stdout.write(
            f"{report['path']}: аватаров {report['avatar']}, рамок {report['frame']}, "
            f"знаков лиг {report['league']}, {report['bytes'] // 1024} КБ"
        )
