"""Checks for the local Django and PostGIS foundation."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
import sentry_sdk
from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point
from django.core.exceptions import DisallowedHost
from django.db import DatabaseError, connection
from django.test import Client
from django.utils import timezone
from config.settings import database_config, sentry_before_send
import pyarrow as pa
import pyarrow.parquet as pq


class GeometrySample(models.Model):
    """Temporary geometry model used only by the integration check."""

    location = models.PointField(srid=4326)

    class Meta:
        app_label = "application_setup_test"
        managed = False


@pytest.fixture
def geometry_table() -> Iterator[None]:
    with connection.schema_editor() as schema_editor:
        schema_editor.create_model(model=GeometrySample)
    try:
        yield
    finally:
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(model=GeometrySample)


@pytest.mark.django_db
def test_health_endpoint_reports_available_application_and_database() -> None:
    response = Client().get(path="/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"application": "available", "database": "available"}


@pytest.mark.django_db
def test_health_endpoint_hides_database_error_details() -> None:
    fake_secret = "password=health-test-secret"
    with patch(
        target="config.health.connection.cursor",
        side_effect=DatabaseError(fake_secret),
    ):
        response = Client().get(path="/api/v1/health")

    assert response.status_code == 503
    assert response.json() == {"application": "available", "database": "unavailable"}
    assert fake_secret not in response.content.decode("utf-8")


@pytest.mark.django_db
def test_dokku_health_page_returns_200_with_a_working_database() -> None:
    response = Client().get(path="/health/")

    assert response.status_code == 200
    assert response.content == b"ok"


@pytest.mark.django_db
def test_health_page_answers_head_requests_from_the_uptime_monitor() -> None:
    response = Client().head(path="/health/")

    assert response.status_code == 200


def test_health_page_refuses_post_requests() -> None:
    response = Client().post(path="/health/")

    assert response.status_code == 405


@pytest.mark.django_db
def test_dokku_health_page_returns_503_when_the_database_query_fails() -> None:
    fake_secret = "password=health-test-secret"
    with patch(
        target="config.health.connection.cursor",
        side_effect=DatabaseError(fake_secret),
    ):
        response = Client().get(path="/health/")

    assert response.status_code == 503
    assert fake_secret not in response.content.decode("utf-8")


@pytest.mark.django_db
def test_dokku_health_page_sets_no_cookie_and_calls_no_outside_service() -> None:
    with patch(
        target="socket.socket.connect",
        side_effect=AssertionError("the health page opened a network connection"),
    ):
        response = Client(headers={"accept-language": "it"}).get(path="/health/")

    assert response.status_code == 200
    assert response.cookies == {}
    assert "Set-Cookie" not in response.headers


@pytest.mark.django_db
def test_dokku_health_page_skips_the_https_redirect(settings) -> None:
    settings.SECURE_SSL_REDIRECT = True

    response = Client().get(path="/health/")

    assert response.status_code == 200


@pytest.mark.django_db
def test_postgis_version_is_available() -> None:
    with connection.cursor() as cursor:
        cursor.execute(sql="SELECT PostGIS_Version()")
        version = cursor.fetchone()[0]

    assert isinstance(version, str)
    assert version


@pytest.mark.django_db(transaction=True)
def test_postgis_stores_wgs84_geometry_with_coordinate_system(
    geometry_table: None,
) -> None:
    sample = GeometrySample.objects.create(
        location=Point(x=11.2558, y=43.7696, srid=4326),
    )
    stored = GeometrySample.objects.get(pk=sample.pk)

    assert stored.location.srid == 4326
    assert stored.location.x == pytest.approx(11.2558)
    assert stored.location.y == pytest.approx(43.7696)


@pytest.mark.django_db
def test_database_connection_uses_utc_while_product_dates_use_rome() -> None:
    assert settings.TIME_ZONE == "Europe/Rome"
    assert settings.USE_TZ is True
    assert timezone.is_aware(timezone.now())

    with connection.cursor() as cursor:
        cursor.execute(sql="SELECT current_setting('TIMEZONE')")
        database_timezone = cursor.fetchone()[0]

    assert database_timezone == "UTC"


def test_parquet_round_trip_works_after_geodjango_native_loading(tmp_path: Path) -> None:
    table = pa.table({"cell_id": ["500m_E4321500_N2345000"], "score": [0.75]})
    parquet_path = tmp_path / "native-library-compatibility.parquet"

    pq.write_table(table=table, where=parquet_path)
    stored = pq.read_table(source=parquet_path)

    assert stored.to_pydict() == {"cell_id": ["500m_E4321500_N2345000"], "score": [0.75]}


def test_database_url_wins_over_separate_database_values() -> None:
    config = database_config(
        environ={
            "DATABASE_URL": "postgis://dokku:secret@db.internal:5432/production",
            "SPORAMETEO_DB_NAME": "ignored",
            "SPORAMETEO_DB_HOST": "ignored-host",
        }
    )

    assert config["ENGINE"] == "django.contrib.gis.db.backends.postgis"
    assert config["NAME"] == "production"
    assert config["USER"] == "dokku"
    assert config["PASSWORD"] == "secret"
    assert config["HOST"] == "db.internal"
    assert config["PORT"] == 5432
    assert config["CONN_MAX_AGE"] == 0
    assert config["OPTIONS"]["connect_timeout"] == 5


def test_separate_database_values_are_used_without_database_url() -> None:
    config = database_config(
        environ={
            "SPORAMETEO_DB_NAME": "custom",
            "SPORAMETEO_DB_USER": "custom_user",
            "SPORAMETEO_DB_PASSWORD": "custom_password",
            "SPORAMETEO_DB_HOST": "custom-host",
            "SPORAMETEO_DB_PORT": "6543",
        }
    )

    assert config == {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": "custom",
        "USER": "custom_user",
        "PASSWORD": "custom_password",
        "HOST": "custom-host",
        "PORT": "6543",
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 5},
    }


def test_database_defaults_are_used_when_nothing_is_set() -> None:
    config = database_config(environ={})

    assert config["NAME"] == "sporameteo"
    assert config["USER"] == "sporameteo"
    assert config["HOST"] == "127.0.0.1"
    assert config["PORT"] == "5542"
    assert config["OPTIONS"] == {"connect_timeout": 5}


def test_sentry_stays_off_without_a_dsn() -> None:
    assert settings.SENTRY_DSN == ""
    assert sentry_sdk.get_client().is_active() is False


def test_sentry_drops_disallowed_host_errors() -> None:
    event = {"level": "error"}
    hint = {"exc_info": (DisallowedHost, DisallowedHost("bad host"), None)}

    assert sentry_before_send(event=event, hint=hint) is None


def test_sentry_keeps_other_errors() -> None:
    event = {"level": "error"}
    hint = {"exc_info": (ValueError, ValueError("broken"), None)}

    assert sentry_before_send(event=event, hint=hint) == event
