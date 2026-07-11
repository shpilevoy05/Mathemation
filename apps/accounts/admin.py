from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import ParentProfile, StudentProfile, User


class StudentProfileInline(admin.StackedInline):
    model = StudentProfile
    extra = 1
    max_num = 1
    can_delete = True


class ParentProfileInline(admin.StackedInline):
    model = ParentProfile
    extra = 1
    max_num = 1
    can_delete = True


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = (StudentProfileInline, ParentProfileInline)
    list_display = (*DjangoUserAdmin.list_display, "role_display")
    list_filter = (*DjangoUserAdmin.list_filter, "role")
    fieldsets = (*DjangoUserAdmin.fieldsets, ("Роль", {"fields": ("role",)}))
    add_fieldsets = (*DjangoUserAdmin.add_fieldsets, ("Роль", {"fields": ("role",)}))

    @admin.display(description="Роль", ordering="role")
    def role_display(self, obj):
        return obj.get_role_display()


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "target_score", "weekly_hours")
    search_fields = ("user__username",)
    list_select_related = ("user",)


admin.site.register(ParentProfile)
