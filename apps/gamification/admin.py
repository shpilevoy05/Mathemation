from django.contrib import admin

from .models import GamificationProfile, WeeklyQuest


@admin.register(GamificationProfile)
class GamificationProfileAdmin(admin.ModelAdmin):
    list_display = ["student", "xp", "level", "streak_current", "streak_best"]
    search_fields = ["student__user__username"]


@admin.register(WeeklyQuest)
class WeeklyQuestAdmin(admin.ModelAdmin):
    list_display = [
        "student", "week_start", "quest_type", "progress_count",
        "target_count", "completed", "reward_xp",
    ]
    list_filter = ["week_start", "quest_type", "completed"]
    search_fields = ["student__user__username", "title"]

