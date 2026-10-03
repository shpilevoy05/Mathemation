from django.contrib import admin

from .models import (
    GamificationProfile,
    LeagueCohort,
    LeagueMember,
    LeagueSeason,
    LeagueTrophy,
    WeeklyQuest,
)


@admin.register(GamificationProfile)
class GamificationProfileAdmin(admin.ModelAdmin):
    list_display = ["student", "xp", "level", "streak_current", "streak_best",
                    "league", "leagues_enabled"]
    list_filter = ["leagues_enabled", "league"]
    search_fields = ["student__user__username"]


@admin.register(WeeklyQuest)
class WeeklyQuestAdmin(admin.ModelAdmin):
    list_display = [
        "student", "week_start", "quest_type", "progress_count",
        "target_count", "completed", "reward_xp",
    ]
    list_filter = ["week_start", "quest_type", "completed"]
    search_fields = ["student__user__username", "title"]



class LeagueMemberInline(admin.TabularInline):
    model = LeagueMember
    fields = ["student", "is_filler", "xp", "place", "promoted", "coins_awarded"]
    readonly_fields = fields
    extra = 0
    can_delete = False


@admin.register(LeagueSeason)
class LeagueSeasonAdmin(admin.ModelAdmin):
    """Сезон только для чтения: итоги подводятся один раз и правке не подлежат."""

    list_display = ["starts_on", "ends_on", "status", "closed_at"]
    list_filter = ["status"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(LeagueCohort)
class LeagueCohortAdmin(admin.ModelAdmin):
    list_display = ["__str__", "season", "league", "index"]
    list_filter = ["league", "season"]
    inlines = [LeagueMemberInline]


@admin.register(LeagueTrophy)
class LeagueTrophyAdmin(admin.ModelAdmin):
    list_display = ["student", "league", "season", "prize", "created_at"]
    list_filter = ["league"]
    search_fields = ["student__user__username"]
