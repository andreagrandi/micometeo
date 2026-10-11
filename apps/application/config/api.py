"""Django Ninja endpoints for the local application."""

from typing import Literal

from django.http import HttpRequest
from django.db import DatabaseError, connection
from ninja import NinjaAPI, Schema, Status


class HealthResponse(Schema):
    """Report whether the application and database can answer requests."""

    application: Literal["available"]
    database: Literal["available", "unavailable"]


api = NinjaAPI(title="Micometeo API", version="1")


@api.get("/health", response={200: HealthResponse, 503: HealthResponse})
def health(request: HttpRequest) -> HealthResponse | Status[HealthResponse]:
    """Return application availability and a database connection check."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql="SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return Status(503, HealthResponse(application="available", database="unavailable"))
    return HealthResponse(application="available", database="available")
