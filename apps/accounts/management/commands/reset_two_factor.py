"""Снять второй фактор с аккаунта из консоли сервера.

Нужен для случая, который иначе не лечится: единственный администратор потерял
телефон и резервные коды. Через интерфейс он войти не может, а снять фактор в
админке может только вошедший — замкнутый круг, из-за которого включение
второго фактора рискует заблокировать команду на проде.

Доступ к консоли сервера здесь и есть право на это действие. Само снятие
пишется в тот же журнал, что и действия из панели.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.accounts.two_factor_services import reset_device


class Command(BaseCommand):
    help = "Снять второй фактор с пользователя (потерян телефон и резервные коды)."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Логин сотрудника")

    def handle(self, *args, **options):
        username = options["username"]
        user = User.objects.filter(username=username).first()
        if user is None:
            raise CommandError(f"Пользователь {username} не найден.")
        if not reset_device(user):
            self.stdout.write(f"У {username} второй фактор не настроен — снимать нечего.")
            return
        self.stdout.write(
            f"Второй фактор снят: {username}. При следующем входе он настроит его заново."
        )
