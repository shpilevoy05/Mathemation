from django.contrib import admin

from .models import KnowledgeDependency, KnowledgeNode, SkillMastery, TopicCluster


class DependencyInline(admin.TabularInline):
    model = KnowledgeDependency
    fk_name = "node"
    extra = 1


@admin.register(KnowledgeNode)
class KnowledgeNodeAdmin(admin.ModelAdmin):
    list_display = ["code", "title", "cluster", "weight", "exam_part"]
    inlines = [DependencyInline]


admin.site.register(TopicCluster)
admin.site.register(KnowledgeDependency)
admin.site.register(SkillMastery)
