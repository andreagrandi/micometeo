"""Django Ninja endpoints for the local application."""

from typing import Literal

from django.http import HttpRequest
from django.db import DatabaseError, connection
from ninja import NinjaAPI, Schema, Status

from area_api.router import router as area_router
from map_api.api import router as map_router
from place_search.api import router as place_search_router


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


api.add_router("", area_router)
api.add_router("", map_router)
api.add_router("", place_search_router)
