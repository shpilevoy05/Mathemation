from django.contrib import admin

from .models import MockExam, MockExamResult

admin.site.register(MockExam)
admin.site.register(MockExamResult)
