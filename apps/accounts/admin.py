from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import ParentProfile, StudentProfile, TwoFactorDevice, User


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


@admin.register(TwoFactorDevice)
class TwoFactorDeviceAdmin(admin.ModelAdmin):
    """Только просмотр и снятие фактора.

    Секрет и отпечатки резервных кодов не редактируются: правка руками либо
    ломает доступ сотруднику, либо тихо ослабляет защиту. Потерянный телефон
    лечится удалением устройства — это действие попадает в журнал.
    """

    list_display = ("user", "is_confirmed", "recovery_left", "last_used_at")
    search_fields = ("user__username",)
    list_select_related = ("user",)
    readonly_fields = (
        "user", "secret", "confirmed_at", "last_step", "recovery_hashes",
        "created_at", "last_used_at",
    )

    def has_add_permission(self, request):
        return False

    @admin.display(boolean=True, description="Подтверждён")
    def is_confirmed(self, obj):
        return obj.is_confirmed

    @admin.display(description="Резервных кодов")
    def recovery_left(self, obj):
        return obj.recovery_left

    def delete_model(self, request, obj):
        from .two_factor_services import reset_device

        reset_device(obj.user, actor=request.user)

    def delete_queryset(self, request, queryset):
        from .two_factor_services import reset_device

        for device in queryset.select_related("user"):
            reset_device(device.user, actor=request.user)
