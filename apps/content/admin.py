from django.contrib import admin
from django.db import models

from .models import Assignment, AssignmentSkillTag, Lesson, TheoryBlock

LATEX_HELP_TEXT = "Формулы: $...$ (строчные), $$...$$ (выносные), LaTeX-синтаксис KaTeX."


class TheoryBlockInline(admin.TabularInline):
    model = TheoryBlock
    extra = 1
    formfield_overrides = {models.TextField: {"help_text": LATEX_HELP_TEXT}}


class SkillTagInline(admin.TabularInline):
    model = AssignmentSkillTag
    extra = 1


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
    list_display = ["title", "exam_part", "difficulty", "max_score"]
    search_fields = ["title", "statement"]
    inlines = [SkillTagInline]
    formfield_overrides = {models.TextField: {"help_text": LATEX_HELP_TEXT}}


@admin.register(TheoryBlock)
class TheoryBlockAdmin(admin.ModelAdmin):
    formfield_overrides = {models.TextField: {"help_text": LATEX_HELP_TEXT}}


admin.site.register(AssignmentSkillTag)
