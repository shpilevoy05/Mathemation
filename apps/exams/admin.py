from django.contrib import admin

from .models import ExamProfile, ExamTask, ExamTaskSkill


class ExamTaskSkillInline(admin.TabularInline):
    model = ExamTaskSkill
    extra = 1
    autocomplete_fields = ["node"]


class ExamTaskInline(admin.TabularInline):
    model = ExamTask
    extra = 0
    fields = ["number", "exam_part", "max_score", "difficulty"]
    show_change_link = True


@admin.register(ExamProfile)
class ExamProfileAdmin(admin.ModelAdmin):
    list_display = ["year", "title", "max_primary_score", "is_active", "task_count"]
    list_filter = ["is_active"]
    inlines = [ExamTaskInline]

    @admin.display(description="Заданий")
    def task_count(self, obj):
        return obj.tasks.count()


@admin.register(ExamTask)
class ExamTaskAdmin(admin.ModelAdmin):
    list_display = ["profile", "number", "exam_part", "max_score", "difficulty"]
    list_filter = ["profile", "exam_part", "difficulty"]
    inlines = [ExamTaskSkillInline]
