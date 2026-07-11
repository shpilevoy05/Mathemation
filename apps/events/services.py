from .models import Event

FORBIDDEN_PERSONAL_DATA_KEYS = {"name", "full_name", "email", "username", "phone"}


def _contains_personal_data_key(value) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower() in FORBIDDEN_PERSONAL_DATA_KEYS
            or _contains_personal_data_key(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_personal_data_key(item) for item in value)
    return False


def log_event(event_type: str, student=None, **payload) -> Event:
    """Единственная точка записи учебных событий.

    Payload должен содержать только идентификаторы и учебные метрики — без
    имён, e-mail и других персональных данных.
    """
    if event_type not in Event.Type.values:
        raise ValueError(f"Неизвестный тип события: {event_type}")
    if _contains_personal_data_key(payload):
        raise ValueError("Payload события не должен содержать персональные данные.")
    return Event.objects.create(student=student, event_type=event_type, payload=payload)
