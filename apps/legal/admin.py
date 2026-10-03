from django.contrib import admin

from .models import ConsentRecord, DataDeletionRequest, Feedback


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "document_version", "subject_student", "accepted_at")
    list_filter = ("kind", "document_version")
    readonly_fields = [field.name for field in ConsentRecord._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DataDeletionRequest)
class DataDeletionRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "created_at", "processed_by", "processed_at")
    list_filter = ("status",)
    readonly_fields = ("user", "created_at", "status", "processed_by", "processed_at", "comment")

    def has_add_permission(self, request):
        return False


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "page_url", "created_at")
    list_filter = ("status",)
