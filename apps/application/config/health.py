"""Health check used by Dokku and the uptime monitor."""

from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_GET


def database_is_available() -> bool:
    """Run a trivial query and report whether the database answered."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql="SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return False
    return True


@require_GET
def health(request: HttpRequest) -> HttpResponse:
    """Answer 200 when the database answers a query and 503 when it does not.
    The age of the weather and estimates is left to the nightly email."""
    if database_is_available():
        return HttpResponse(content="ok", content_type="text/plain")
    return HttpResponse(content="database unavailable", content_type="text/plain", status=503)
