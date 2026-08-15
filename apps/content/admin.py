from django.contrib import admin

from .models import (
    Assignment,
    AssignmentSkillTag,
    Lesson,
    SolutionPath,
    SolutionStep,
    TheoryBlock,
)


class TheoryBlockInline(admin.TabularInline):
    model = TheoryBlock
    extra = 1


class SkillTagInline(admin.TabularInline):
    model = AssignmentSkillTag
    extra = 1


class SolutionPathInline(admin.TabularInline):
    model = SolutionPath
    fields = ["code", "title", "path_type", "selection_method", "is_active", "order"]
    extra = 0
    show_change_link = True
    verbose_name = "путь решения"
    verbose_name_plural = "Пути решения"


class SolutionStepInline(admin.TabularInline):
    model = SolutionStep
    fields = ["order", "stage", "node", "role", "signal", "is_required", "description"]
    autocomplete_fields = ["node"]
    extra = 1
    verbose_name = "шаг пути"
    verbose_name_plural = "Шаги пути"


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ["title", "node", "order", "has_video"]
    search_fields = ["title", "node__title", "node__code"]
    fields = ["node", "title", "order", "video_url", "video_duration_minutes"]
    inlines = [TheoryBlockInline]

    @admin.display(boolean=True, description="Видео")
    def has_video(self, obj):
        return bool(obj.video_url)


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ["title", "exam_part", "answer_type", "difficulty", "max_score"]
    list_filter = ["exam_part", "answer_type"]
    search_fields = ["title", "statement"]
    inlines = [SkillTagInline, SolutionPathInline]


admin.site.register(TheoryBlock)
admin.site.register(AssignmentSkillTag)


@admin.register(SolutionPath)
class SolutionPathAdmin(admin.ModelAdmin):
    list_display = ["code", "title", "assignment", "path_type", "is_active"]
    list_filter = ["path_type", "is_active"]
    search_fields = ["code", "title", "assignment__title"]
    autocomplete_fields = ["assignment"]
    inlines = [SolutionStepInline]
