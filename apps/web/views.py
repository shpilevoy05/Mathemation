"""Server-rendered student cabinet views."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.practice.models import Attempt

from . import services
from .permissions import is_expert, is_methodist


def _render_student_page(request, template_name, context_factory, *args, **kwargs):
    student = getattr(request.user, "student_profile", None)
    context = {"student": student}
    if student is not None:
        context.update(context_factory(student, *args, **kwargs))
    return render(request, template_name, context)


@login_required
def dashboard(request):
    student = getattr(request.user, "student_profile", None)
    if student is None:
        if request.user.is_superuser:
            return redirect("admin:index")
        if is_expert(request.user):
            return redirect("expert_queue")
        if is_methodist(request.user):
            return redirect("methodist_dashboard")
        if getattr(request.user, "parent_profile", None) is not None:
            return redirect("parent_dashboard")
        if request.user.is_staff:
            return redirect("admin:index")
        return render(request, "dashboard.html", {"student": None})
    show_week_plan = not request.session.get("week_plan_shown", False)
    if show_week_plan:
        request.session["week_plan_shown"] = True
    context = {"student": student, "show_week_plan": show_week_plan}
    context.update(services.dashboard_context(student))
    return render(request, "dashboard.html", context)


@login_required
def knowledge_map(request):
    return _render_student_page(
        request,
        "knowledge_map.html",
        services.knowledge_map_context,
        overlay=request.GET.get("overlay") == "ceiling",
    )


@login_required
def knowledge_node(request, node_id):
    return _render_student_page(
        request, "knowledge_node.html", services.knowledge_node_context, node_id=node_id
    )


@login_required
def track(request):
    return _render_student_page(request, "track.html", services.track_context)


@login_required
def lesson(request, node_id):
    context = request.GET.get("context", Attempt.Context.LESSON)
    return _render_student_page(
        request,
        "lesson.html",
        services.lesson_context,
        node_id=node_id,
        attempt_context=context,
    )


@login_required
def practice_backlog(request):
    return _render_student_page(
        request, "practice_backlog.html", services.practice_backlog_context
    )


@login_required
def forecast(request):
    return _render_student_page(request, "forecast.html", services.forecast_context)


@login_required
def diagnostics(request):
    return _render_student_page(
        request, "diagnostics.html", services.diagnostics_context
    )


@login_required
def diagnostic_run(request, result_id):
    return _render_student_page(
        request,
        "diagnostic_run.html",
        services.diagnostic_run_context,
        result_id=result_id,
    )


@login_required
def mocks(request):
    return _render_student_page(request, "mocks.html", services.mocks_context)


@login_required
def mock_run(request, result_id):
    return _render_student_page(
        request, "mock_run.html", services.mock_run_context, result_id=result_id
    )


@login_required
def mock_result(request, result_id):
    return _render_student_page(
        request, "mock_result.html", services.mock_result_context, result_id=result_id
    )


@login_required
def parent_dashboard(request):
    parent = getattr(request.user, "parent_profile", None)
    context = {"parent": parent}
    if parent is not None:
        context.update(services.parent_context(parent))
    return render(request, "parent_dashboard.html", context)


@login_required
def expert_queue(request):
    allowed = is_expert(request.user)
    context = {"allowed": allowed}
    if allowed:
        context.update(services.expert_queue_context(request.user))
    return render(request, "expert/queue.html", context)


@login_required
def expert_review(request, review_id):
    allowed = is_expert(request.user)
    context = {"allowed": allowed}
    if allowed:
        context.update(services.expert_review_context(review_id))
    return render(request, "expert/review.html", context)


@login_required
def methodist_dashboard(request):
    allowed = is_methodist(request.user)
    context = {"allowed": allowed}
    if allowed:
        context.update(services.methodist_context())
    return render(request, "methodist/dashboard.html", context)
