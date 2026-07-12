from django.contrib import admin

from apps.content.models import AssignmentSkillTag, Lesson

from .models import KnowledgeDependency, KnowledgeNode, SkillMastery, TopicCluster


class DependencyInline(admin.TabularInline):
    model = KnowledgeDependency
    fk_name = "node"
    fields = ["prerequisite", "min_mastery"]
    autocomplete_fields = ["prerequisite"]
    extra = 1
    verbose_name = "условие открытия (родительская тема)"
    verbose_name_plural = "Условия открытия (родительские темы)"


class ReverseDependencyInline(admin.TabularInline):
    model = KnowledgeDependency
    fk_name = "prerequisite"
    fields = ["node", "min_mastery"]
    autocomplete_fields = ["node"]
    extra = 1
    verbose_name = "открываемая тема (дочерняя)"
    verbose_name_plural = "Открывает темы (дочерние)"


class LessonInline(admin.TabularInline):
    model = Lesson
    fields = ["title", "order", "video_url"]
    extra = 1
    verbose_name = "урок темы"
    verbose_name_plural = "Уроки темы"


class AssignmentSkillTagInline(admin.TabularInline):
    model = AssignmentSkillTag
    fk_name = "node"
    fields = ["assignment", "weight"]
    autocomplete_fields = ["assignment"]
    extra = 1
    verbose_name = "задача темы"
    verbose_name_plural = "Задачи темы"


@admin.register(KnowledgeNode)
class KnowledgeNodeAdmin(admin.ModelAdmin):
    list_display = ["code", "title", "cluster", "weight", "exam_part"]
    search_fields = ["code", "title"]
    inlines = [
        DependencyInline,
        ReverseDependencyInline,
        LessonInline,
        AssignmentSkillTagInline,
    ]


@admin.register(KnowledgeDependency)
class KnowledgeDependencyAdmin(admin.ModelAdmin):
    list_display = ["node", "prerequisite", "min_mastery"]
    autocomplete_fields = ["node", "prerequisite"]


admin.site.register(TopicCluster)
admin.site.register(SkillMastery)
