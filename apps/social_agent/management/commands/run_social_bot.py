import time

from django.core.management.base import BaseCommand

from ...bot import process_updates


class Command(BaseCommand):
    help = "Запустить long-polling бота согласования публикаций"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Обработать один запрос getUpdates и выйти")

    def handle(self, *args, **options):
        try:
            while True:
                process_updates()
                if options["once"]:
                    return
                time.sleep(1)
        except KeyboardInterrupt:
            self.stdout.write("Бот остановлен")
