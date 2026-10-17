"""URL routes for the local SporaMeteo application."""

from django.urls import path

from .api import api
from .health import health
from web_ui import views as web_views


urlpatterns = [
    path("health/", health, name="health"),
    path("", web_views.landing, name="landing"),
    path("map/", web_views.map_page, name="map"),
    path("map/fixture/<str:fixture>/", web_views.map_page, name="map-fixture"),
    path("privacy/", web_views.privacy, name="privacy"),
    path("api/v1/", api.urls),
]
