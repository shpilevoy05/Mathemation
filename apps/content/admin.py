from django.contrib import admin

from .models import Assignment, AssignmentSkillTag, Lesson, TheoryBlock


class TheoryBlockInline(admin.TabularInline):
    model = TheoryBlock
    extra = 1


class SkillTagInline(admin.TabularInline):
    model = AssignmentSkillTag
    extra = 1


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ["title", "node", "order"]
    inlines = [TheoryBlockInline]


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ["title", "exam_part", "difficulty", "max_score"]
    inlines = [SkillTagInline]
