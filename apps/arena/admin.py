from django.contrib import admin

from .models import Friendship, Match, MatchAnswer, MatchParticipant, MatchQuestion


class ParticipantInline(admin.TabularInline):
    model = MatchParticipant
    fields = ["student", "is_bot", "score", "correct_count", "total_time_ms", "finished_at"]
    readonly_fields = fields
    extra = 0
    can_delete = False


class QuestionInline(admin.TabularInline):
    model = MatchQuestion
    fields = ["order", "assignment", "points"]
    readonly_fields = fields
    extra = 0
    can_delete = False


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    """Только чтение: результат партии — история, а не редактируемая запись."""

    list_display = ["id", "mode", "status", "created_by", "bot_level", "created_at"]
    list_filter = ["mode", "status"]
    search_fields = ["created_by__user__username"]
    inlines = [ParticipantInline, QuestionInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ["from_student", "to_student", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["from_student__user__username", "to_student__user__username"]


admin.site.register(MatchAnswer)
