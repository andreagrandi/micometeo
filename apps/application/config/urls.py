"""URL routes for the local Micometeo application."""

from django.urls import path

from .api import api
from web_ui import views as web_views


urlpatterns = [
    path("", web_views.landing, name="landing"),
    path("map/", web_views.map_page, name="map"),
    path("map/fixture/<str:fixture>/", web_views.map_page, name="map-fixture"),
    path("api/v1/", api.urls),
]
