from django.contrib import admin

from .models import AiHintMessage, AiHintSession


class AiHintMessageInline(admin.TabularInline):
    model = AiHintMessage
    extra = 0
    fields = (
        "role",
        "text",
        "is_blocked",
        "failed_claims",
        "unverified_claims",
        "created_at",
    )
    readonly_fields = fields
    can_delete = False


@admin.register(AiHintSession)
class AiHintSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "student",
        "assignment",
        "hints_used",
        "escalated_to_expert",
        "created_at",
    )
    list_filter = ("escalated_to_expert", "created_at")
    inlines = (AiHintMessageInline,)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if (
            not request.user.is_superuser
            and request.user.groups.filter(name="Эксперты").exists()
        ):
            return queryset.filter(escalated_to_expert=True)
        return queryset


@admin.register(AiHintMessage)
class AiHintMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "role", "is_blocked", "created_at")
    list_filter = ("role", "is_blocked", "created_at")
    readonly_fields = (
        "session",
        "role",
        "text",
        "is_blocked",
        "failed_claims",
        "unverified_claims",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
