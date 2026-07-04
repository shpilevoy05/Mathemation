from django.contrib import admin

from .models import ExpertReviewRequest


@admin.register(ExpertReviewRequest)
class ExpertReviewRequestAdmin(admin.ModelAdmin):
    list_display = ["id", "student", "assignment", "status", "created_at", "reviewed_at"]
    list_filter = ["status"]
