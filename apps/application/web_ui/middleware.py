from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.middleware.locale import LocaleMiddleware
from django.utils import translation


class WebUILocaleMiddleware(LocaleMiddleware):
    """Negotiate languages for the public web UI routes only."""

    @staticmethod
    def _is_web_ui_path(path: str) -> bool:
        """Return whether a request belongs to the public web UI."""
        return path == "/" or path.startswith("/map/")

    def process_request(self, request: HttpRequest) -> None:
        """Activate browser or cookie language for public UI requests."""
        if self._is_web_ui_path(request.path_info):
            super().process_request(request)
            return
        translation.activate(settings.LANGUAGE_CODE)
        request.LANGUAGE_CODE = translation.get_language()

    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        """Leave API responses in the configured language without headers."""
        if self._is_web_ui_path(request.path_info):
            return super().process_response(request, response)
        translation.activate(settings.LANGUAGE_CODE)
        request.LANGUAGE_CODE = translation.get_language()
        return response
