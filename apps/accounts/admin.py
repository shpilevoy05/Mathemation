from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ParentProfile, StudentProfile, User

admin.site.register(User, UserAdmin)
admin.site.register(StudentProfile)
admin.site.register(ParentProfile)
