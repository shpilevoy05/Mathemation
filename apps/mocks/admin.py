from django.contrib import admin

from .models import MockExam, MockExamResult

@admin.register(MockExam)
class MockExamAdmin(admin.ModelAdmin):
    list_display = ["title", "kind", "duration_minutes", "is_active"]
    list_filter = ["kind", "is_active"]


admin.site.register(MockExamResult)
