from django.contrib import admin

from .models import DiagnosticResult, DiagnosticTest

admin.site.register(DiagnosticTest)
admin.site.register(DiagnosticResult)
