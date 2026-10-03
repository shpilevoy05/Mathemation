from django.contrib import admin

from .models import Friendship, Match, MatchAnswer, MatchParticipant, MatchQuestion


class ParticipantInline(admin.TabularInline):
    model = MatchParticipant
    fields = ["student", "is_bot", "score", "correct_count", "total_time_ms",
              "joined_at", "started_at", "finished_at"]
    readonly_fields = fields
    extra = 0
    can_delete = False


class QuestionInline(admin.TabularInline):
    """Вопросы партии: задача или теория, цена клетки и что было разыграно.

    Прогон бота виден здесь же: при разборе спорной партии первый вопрос —
    «что бот вообще знал», и ответ на него должен быть под рукой.
    """

    model = MatchQuestion
    fields = ["order", "column", "topic_title", "assignment", "theory", "points",
              "opened_at", "picked_by", "resolved_by", "bot_correct", "bot_time_ms"]
    readonly_fields = fields
    extra = 0
    can_delete = False


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    """Только чтение: результат партии — история, а не редактируемая запись."""

    list_display = ["id", "mode", "status", "limit_kind", "created_by", "bot_level",
                    "turn_participant", "revision", "created_at"]
    list_filter = ["mode", "status", "limit_kind"]
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
