from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["id", "event_type", "student", "created_at"]
    list_filter = ["event_type", "created_at"]
    readonly_fields = ["student", "event_type", "payload", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

