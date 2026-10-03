from django.contrib import admin, messages
from django.utils import timezone

from . import services
from .models import (BotState, BrandProfile, Channel, ContentIdea, LlmCall, MediaAsset, Post, PostCheck, Rubric, RubricSlot, SocialLessonPermission, SocialTaskPermission)


class PostCheckInline(admin.TabularInline):
    model = PostCheck
    extra = 0
    can_delete = False
    readonly_fields = ("kind", "passed", "detail")


class LlmCallInline(admin.TabularInline):
    model = LlmCall
    extra = 0
    can_delete = False
    readonly_fields = ("purpose", "model", "prompt_tokens", "completion_tokens", "cost", "created_at")


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "rubric", "channel", "status", "scheduled_for")
    list_filter = ("status", "channel", "rubric")
    actions = ("approve_selected", "reject_selected")
    inlines = (PostCheckInline, LlmCallInline)

    @admin.action(description="Одобрить выбранные публикации")
    def approve_selected(self, request, queryset):
        changed = 0
        for post in queryset:
            try:
                services.approve_post(post, reason="Одобрено в админке")
                changed += 1
            except services.InvalidTransition:
                continue
        self.message_user(request, f"Одобрено: {changed}", messages.SUCCESS)

    @admin.action(description="Отклонить выбранные публикации")
    def reject_selected(self, request, queryset):
        changed = 0
        for post in queryset:
            try:
                services.reject_post(post, reason="Отклонено в админке")
                changed += 1
            except services.InvalidTransition:
                continue
        self.message_user(request, f"Отклонено: {changed}", messages.SUCCESS)


@admin.register(BrandProfile)
class BrandProfileAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not BrandProfile.objects.exists() and super().has_add_permission(request)


class RubricSlotInline(admin.TabularInline):
    model = RubricSlot
    extra = 0


@admin.register(Rubric)
class RubricAdmin(admin.ModelAdmin):
    inlines = (RubricSlotInline,)
    list_display = ("title", "audience", "source_kind", "risk", "is_active")


class PermissionAdmin(admin.ModelAdmin):
    readonly_fields = ("approved_by", "approved_at")

    def save_model(self, request, obj, form, change):
        obj.approved_by = request.user
        obj.approved_at = timezone.now()
        super().save_model(request, obj, form, change)


admin.site.register(Channel)
admin.site.register(ContentIdea)
admin.site.register(SocialTaskPermission, PermissionAdmin)
admin.site.register(SocialLessonPermission, PermissionAdmin)
admin.site.register(MediaAsset)


@admin.register(BotState)
class BotStateAdmin(admin.ModelAdmin):
    readonly_fields = ("key", "value")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
