from django.http import JsonResponse
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode

from .services import has_current_consents, is_consent_exempt


class ConsentRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.LEGAL_CONSENT_ENFORCED:
            return self.get_response(request)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or is_consent_exempt(user):
            return self.get_response(request)
        allowed = (
            reverse("legal_accept"), reverse("legal_privacy"), reverse("legal_terms"),
            reverse("logout"), "/static/",
        )
        if any(request.path.startswith(prefix) for prefix in allowed):
            return self.get_response(request)
        if not has_current_consents(user):
            if request.path.startswith("/api/"):
                return JsonResponse(
                    {"detail": "Необходимо принять актуальные документы.",
                     "code": "consent_required"},
                    status=403,
                )
            return redirect(f"{reverse('legal_accept')}?{urlencode({'next': request.get_full_path()})}")
        return self.get_response(request)
