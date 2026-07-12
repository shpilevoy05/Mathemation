"""Role checks shared by back-office web pages and API permissions."""

from apps.accounts.models import User


def _has_access(user, *, role, group_name):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.role == role:
        return True
    return user.groups.filter(name=group_name).exists()


def is_expert(user):
    return _has_access(user, role=User.Role.EXPERT, group_name="Эксперты")


def is_methodist(user):
    return _has_access(user, role=User.Role.METHODIST, group_name="Методисты")
