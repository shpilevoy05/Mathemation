from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.http import StreamingHttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.throttling import client_ip

from .forms import ConsentAcceptanceForm, DataDeletionRequestForm
from .models import DataDeletionRequest
from .services import export_user_data, record_current_consents, request_data_deletion


def privacy(request):
    return render(request, "legal/privacy.html", {
        "draft": settings.LEGAL_DOCS_DRAFT,
        "version": settings.LEGAL_DOCUMENT_VERSIONS["privacy"],
    })


def terms(request):
    return render(request, "legal/terms.html", {
        "draft": settings.LEGAL_DOCS_DRAFT,
        "version": settings.LEGAL_DOCUMENT_VERSIONS["terms"],
    })


@login_required
def accept_documents(request):
    form = ConsentAcceptanceForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        record_current_consents(
            request.user,
            ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            subject_students=form.children,
        )
        target = request.POST.get("next") or request.GET.get("next") or reverse("dashboard")
        if not url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            target = reverse("dashboard")
        return redirect(target)
    return render(request, "legal/accept.html", {
        "form": form,
        "next": request.GET.get("next", ""),
        "hide_nav": True,
    })


@login_required
def download_user_data(request):
    encoder = DjangoJSONEncoder(ensure_ascii=False, indent=2)
    response = StreamingHttpResponse(
        encoder.iterencode(export_user_data(request.user)),
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = 'attachment; filename="matemacia-data.json"'
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
def create_deletion_request(request):
    if request.method != "POST":
        return redirect("account_settings")
    form = DataDeletionRequestForm(request.POST, user=request.user)
    if form.is_valid():
        request_data_deletion(request.user)
        messages.success(request, "Запрос на удаление аккаунта создан.")
    else:
        messages.error(request, "Не удалось создать запрос: проверьте пароль.")
    return redirect("account_settings")


def latest_deletion_request(user):
    return DataDeletionRequest.objects.filter(user=user).first()
