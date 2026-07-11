from django.contrib import admin
from django.db import connection
from django.db.models import DateTimeField, DurationField, ExpressionWrapper, F, Func, Value
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.html import format_html

from .forms import FinishExpertReviewForm

from .models import ExpertReviewRequest


@admin.register(ExpertReviewRequest)
class ExpertReviewRequestAdmin(admin.ModelAdmin):
    form = FinishExpertReviewForm
    list_display = ["id", "student", "assignment", "status", "sla_state", "reviewed_at"]
    list_filter = ["status"]
    ordering = []
    readonly_fields = ["status", "reviewer", "total_score", "lost_points", "reviewed_at"]
    fields = [
        "student", "assignment", "attempt", "mock_result", "solution_file", "status",
        "sla_hours", "reviewer", "score_by_criteria", "total_score", "lost_points",
        "comment", "error_tags", "related_nodes", "needs_resubmission", "finish_review",
        "reviewed_at",
    ]

    def save_model(self, request, obj, form, change):
        if form.cleaned_data.get("finish_review"):
            from .services import finish_review

            finish_review(
                obj,
                request.user,
                form.cleaned_data["score_by_criteria"],
                comment=form.cleaned_data.get("comment", ""),
                related_node_ids=form.cleaned_data.get("related_nodes"),
                error_tags=form.cleaned_data.get("error_tags"),
                needs_resubmission=form.cleaned_data.get("needs_resubmission", False),
            )
        else:
            super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        if connection.vendor == "postgresql":
            sla_duration = Func(
                F("sla_hours"),
                function="make_interval",
                template="make_interval(hours => %(expressions)s)",
                output_field=DurationField(),
            )
        else:
            # SQLite stores DurationField values as microseconds.
            sla_duration = Cast(
                F("sla_hours") * Value(60 * 60 * 1_000_000),
                output_field=DurationField(),
            )
        return super().get_queryset(request).annotate(
            _sla_deadline=ExpressionWrapper(
                F("created_at") + sla_duration,
                output_field=DateTimeField(),
            )
        ).order_by("_sla_deadline")

    def get_readonly_fields(self, request, obj=None):
        fields = list(self.readonly_fields)
        if obj and obj.reviewed_at:
            fields.extend(["score_by_criteria", "comment", "error_tags", "related_nodes"])
        return fields

    @admin.display(description="SLA-дедлайн", ordering="_sla_deadline")
    def sla_state(self, obj):
        deadline = obj.created_at + timezone.timedelta(hours=obj.sla_hours)
        label = timezone.localtime(deadline).strftime("%d.%m.%Y %H:%M")
        if obj.reviewed_at is None and deadline < timezone.now():
            return format_html('<strong style="color:#ba2121">{} · просрочено</strong>', label)
        return label
