from django.contrib import admin

from .models import PlanChangeLog, StudyPlan, StudyPlanItem


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
