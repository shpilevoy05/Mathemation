from django.apps import AppConfig


class SocialAgentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.social_agent"
    verbose_name = "Агент социальных сетей"

    def ready(self):
        from .adapters import telegram  # noqa: F401
