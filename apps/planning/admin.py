from django.contrib import admin

from .models import (
    PlanChangeLog,
    StudyPlan,
    StudyPlanItem,
    Trajectory,
    TrajectoryTransition,
)


@admin.register(Trajectory)
class TrajectoryAdmin(admin.ModelAdmin):
    list_display = ["slug", "title", "target_min", "target_max", "weekly_load_hours"]


@admin.register(TrajectoryTransition)
class TrajectoryTransitionAdmin(admin.ModelAdmin):
    list_display = ["student", "from_trajectory", "to_trajectory", "acknowledged", "created_at"]
    list_filter = ["acknowledged", "to_trajectory"]


class StudyPlanItemInline(admin.TabularInline):
    model = StudyPlanItem
    extra = 0


@admin.register(StudyPlan)
class StudyPlanAdmin(admin.ModelAdmin):
    list_display = ["id", "student", "target_score", "status", "created_at"]
    list_filter = ["status"]
    inlines = [StudyPlanItemInline]


@admin.register(PlanChangeLog)
class PlanChangeLogAdmin(admin.ModelAdmin):
    list_display = ["id", "plan", "reason", "is_major", "acknowledged", "created_at"]
    list_filter = ["reason", "is_major"]
