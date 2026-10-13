"""Focused checks for place search caching, errors and API contracts."""

from datetime import timedelta
from email.utils import format_datetime
import json
from types import SimpleNamespace
import uuid
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

import pytest
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import Client, override_settings
from django.utils import timezone

from place_search.models import PlaceSearchCache
from place_search.provider import (
    PlaceSearchThrottled,
    PlaceSearchTimeout,
    PlaceSearchUnavailable,
    _request,
    _retry_after,
    cached_place_results,
    normalize_query,
    search_places,
)
from micometeo.finds.grid import format_cell_id
from national_forest.models import ForestBuild
from national_grid.models import GridBuild, GridBuildCell, GridCell, GridChunk, GridRegion
from pyproj import Transformer


def _resolve_post(*, client: Client, latitude: object, longitude: object, source: str = "point"):
    return client.post(
        path="/api/v1/places/resolve",
        data=json.dumps({"latitude": latitude, "longitude": longitude, "source": source}),
        content_type="application/json",
    )


def _photon_feature(*, name: str, longitude: float, latitude: float) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
        "properties": {
            "name": name,
            "city": name,
            "state": "Toscana",
            "countrycode": "IT",
            "osm_id": 123,
        },
    }


@pytest.fixture
def resolve_geometry_fixture() -> dict[str, tuple[float, float] | str]:
    suffix = uuid.uuid4().hex[:10]
    west, south = 4_300_000, 2_300_000
    square_id = format_cell_id(corner_e=west, corner_n=south)
    cell_geometry = Polygon.from_bbox((west, south, west + 500, south + 500))
    region_geometry = Polygon.from_bbox((west - 100, south - 100, west + 600, south + 600))
    grid = GridBuild.objects.create(
        version=f"place-search-grid-{suffix}",
        fingerprint="a" * 64,
        status=GridBuild.Status.COMPLETED,
    )
    region = GridRegion.objects.create(
        build=grid,
        istat_code=f"R{suffix}",
        name=f"Place search region {suffix}",
        geometry=MultiPolygon(region_geometry, srid=3035),
    )
    chunk = GridChunk.objects.create(
        build=grid,
        west_e=west,
        south_n=south,
        east_e=west + 500,
        north_n=south + 500,
        status=GridChunk.Status.COMPLETED,
        cell_count=1,
    )
    cell = GridCell.objects.create(
        cell_id=square_id,
        corner_e=west,
        corner_n=south,
        geometry=cell_geometry,
    )
    GridBuildCell.objects.create(
        build=grid,
        cell=cell,
        chunk=chunk,
        owner_region=region,
        land_geometry=MultiPolygon(cell_geometry, srid=3035),
        land_share=1.0,
    )
    ForestBuild.objects.create(
        version=f"place-search-forest-{suffix}",
        grid_build=grid,
        fingerprint="b" * 64,
        status=ForestBuild.Status.COMPLETED,
    )
    grid_to_wgs84 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)
    center_longitude, center_latitude = grid_to_wgs84.transform(west + 250, south + 250)
    edge_longitude, edge_latitude = grid_to_wgs84.transform(west, south + 250)
    outside_longitude, outside_latitude = grid_to_wgs84.transform(west - 1_000, south - 1_000)
    return {
        "version": f"place-search-forest-{suffix}",
        "square_id": square_id,
        "center": (center_latitude, center_longitude),
        "edge": (edge_latitude, edge_longitude),
        "outside": (outside_latitude, outside_longitude),
    }


@pytest.mark.django_db
@override_settings(MICOMETEO_PLACE_SEARCH_REQUEST_INTERVAL=0)
def test_place_search_normalizes_query_and_reuses_durable_cache() -> None:
    data = {"features": [_photon_feature(name="Pistoia", longitude=10.92, latitude=43.93)]}
    with patch("place_search.provider._request", return_value=data) as request:
        first, first_cached = search_places(query="  PISTOIA ", language="it")
        second, second_cached = search_places(query="pistoia", language="it")

    assert first == second
    assert first[0]["name"] == "Pistoia"
    assert first_cached is False
    assert second_cached is True
    assert request.call_count == 1
    assert PlaceSearchCache.objects.count() == 1
    assert normalize_query("  Pìstoia  ") == "pìstoia"


@pytest.mark.django_db
def test_cached_only_api_returns_exact_cache_without_provider_request() -> None:
    PlaceSearchCache.objects.create(
        normalized_query="pistoia",
        language="it",
        endpoint="https://photon.komoot.io/api",
        results=[{"name": "Pistoia", "latitude": 43.93, "longitude": 10.92}],
        fetched_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
    )
    with (
        patch("place_search.provider._request") as provider_request,
        patch("place_search.provider._throttle") as throttle,
    ):
        response = Client().get(
            path="/api/v1/places/search?q=Pistoia&lang=it&cached_only=1"
        )

    assert response.status_code == 200
    assert response.json() == {
        "results": [{"name": "Pistoia", "latitude": 43.93, "longitude": 10.92}],
        "cached": True,
        "complete": True,
    }
    provider_request.assert_not_called()
    throttle.assert_not_called()


@pytest.mark.django_db
def test_cached_only_api_marks_exact_empty_cache_as_complete() -> None:
    PlaceSearchCache.objects.create(
        normalized_query="abetone",
        language="it",
        endpoint="https://photon.komoot.io/api",
        results=[],
        fetched_at=timezone.now(),
        expires_at=timezone.now() + timedelta(minutes=5),
    )

    response = Client().get(path="/api/v1/places/search?q=Abetone&lang=it&cached_only=1")

    assert response.status_code == 200
    assert response.json() == {"results": [], "cached": True, "complete": True}


@pytest.mark.django_db
def test_cached_only_api_uses_related_rows_without_crossing_cache_namespace() -> None:
    now = timezone.now()
    PlaceSearchCache.objects.create(
        normalized_query="pistoia",
        language="it",
        endpoint="https://photon.komoot.io/api",
        results=[{"name": "Pistoia", "latitude": 43.93, "longitude": 10.92}],
        fetched_at=now,
        expires_at=now + timedelta(days=1),
    )
    PlaceSearchCache.objects.create(
        normalized_query="pistoia",
        language="en",
        endpoint="https://photon.komoot.io/api",
        results=[{"name": "Pistoia English", "latitude": 43.94, "longitude": 10.93}],
        fetched_at=now,
        expires_at=now + timedelta(days=1),
    )
    PlaceSearchCache.objects.create(
        normalized_query="pistoia",
        language="it",
        endpoint="https://other.example/api",
        results=[{"name": "Other Pistoia", "latitude": 43.95, "longitude": 10.94}],
        fetched_at=now,
        expires_at=now + timedelta(days=1),
    )
    PlaceSearchCache.objects.create(
        normalized_query="pistoia-old",
        language="it",
        endpoint="https://photon.komoot.io/api",
        results=[{"name": "Expired Pistoia", "latitude": 43.96, "longitude": 10.95}],
        fetched_at=now - timedelta(days=2),
        expires_at=now - timedelta(minutes=1),
    )

    with patch("place_search.provider._request") as provider_request:
        response = Client().get(
            path="/api/v1/places/search?q=pist&lang=it&cached_only=1"
        )

    assert response.status_code == 200
    assert response.json() == {
        "results": [{"name": "Pistoia", "latitude": 43.93, "longitude": 10.92}],
        "cached": True,
        "complete": False,
    }
    provider_request.assert_not_called()


@pytest.mark.django_db
def test_cached_prefix_preview_is_incomplete_and_never_written_as_exact_cache() -> None:
    now = timezone.now()
    PlaceSearchCache.objects.create(
        normalized_query="marcello",
        language="it",
        endpoint="https://photon.komoot.io/api",
        results=[
            {"name": "San Marcello", "context": "Pistoia", "latitude": 44.0, "longitude": 10.0},
            {"name": "San Marcello", "context": "Pistoia", "latitude": 44.0, "longitude": 10.0},
            {"name": "Piteglio", "context": "Pistoia", "latitude": 44.1, "longitude": 10.1},
        ],
        fetched_at=now,
        expires_at=now + timedelta(days=1),
    )

    results, complete = cached_place_results(query="mar", language="it")

    assert complete is False
    assert results == [
        {"name": "San Marcello", "context": "Pistoia", "latitude": 44.0, "longitude": 10.0}
    ]
    assert not PlaceSearchCache.objects.filter(normalized_query="mar").exists()


@pytest.mark.django_db
@override_settings(
    MICOMETEO_PLACE_SEARCH_REQUEST_INTERVAL=0,
    MICOMETEO_PLACE_SEARCH_CACHE_SECONDS=2_592_000,
    MICOMETEO_PLACE_SEARCH_EMPTY_CACHE_SECONDS=900,
)
def test_place_search_uses_long_positive_and_short_empty_cache_ttls() -> None:
    with patch(
        "place_search.provider._request",
        side_effect=[
            {"features": [_photon_feature(name="Pistoia", longitude=10.92, latitude=43.93)]},
            {"features": []},
        ],
    ):
        search_places(query="Pistoia", language="it")
        search_places(query="Abetone", language="it")

    positive = PlaceSearchCache.objects.get(normalized_query="pistoia")
    empty = PlaceSearchCache.objects.get(normalized_query="abetone")
    assert positive.expires_at - positive.fetched_at == timedelta(days=30)
    assert empty.expires_at - empty.fetched_at == timedelta(minutes=15)


@pytest.mark.django_db
def test_short_place_query_does_not_call_provider() -> None:
    with patch("place_search.provider._request") as request:
        results, cached = search_places(query="P", language="it")

    assert results == []
    assert cached is True
    request.assert_not_called()


@pytest.mark.django_db
@override_settings(MICOMETEO_PLACE_SEARCH_REQUEST_INTERVAL=0)
def test_fresh_search_removes_bounded_expired_entries_and_preserves_live_cache() -> None:
    now = timezone.now()
    PlaceSearchCache.objects.bulk_create(
        [
            PlaceSearchCache(
                normalized_query=f"expired-{index}",
                language="it",
                endpoint="https://photon.komoot.io/api",
                results=[],
                fetched_at=now - timedelta(days=31),
                expires_at=now - timedelta(days=1),
            )
            for index in range(101)
        ]
    )
    live = PlaceSearchCache.objects.create(
        normalized_query="live",
        language="it",
        endpoint="https://photon.komoot.io/api",
        results=[],
        fetched_at=now,
        expires_at=now + timedelta(days=1),
    )
    with patch("place_search.provider._request", return_value={"features": []}):
        search_places(query="Pistoia", language="it")
    assert PlaceSearchCache.objects.filter(expires_at__lte=now).count() == 1
    assert PlaceSearchCache.objects.filter(id=live.id).exists() is True
    assert PlaceSearchCache.objects.filter(normalized_query="pistoia").exists() is True


@pytest.mark.django_db
@override_settings(MICOMETEO_PLACE_SEARCH_REQUEST_INTERVAL=0)
def test_place_search_api_returns_provider_timeout_without_credentials() -> None:
    client = Client()
    with patch(
        "place_search.provider._request",
        side_effect=PlaceSearchTimeout("provider timeout"),
    ):
        response = client.get(path="/api/v1/places/search?q=Abetone")

    assert response.status_code == 504
    assert response.json()["code"] == "provider_timeout"


@pytest.mark.django_db
@override_settings(MICOMETEO_PLACE_SEARCH_REQUEST_INTERVAL=60)
def test_place_search_api_returns_local_throttle_for_a_second_provider_request() -> None:
    data = {"features": []}
    with patch("place_search.provider._request", return_value=data) as request:
        first = Client().get(path="/api/v1/places/search?q=Abetone")
        second = Client().get(path="/api/v1/places/search?q=Femminamorta")

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["code"] == "throttled"
    assert int(second["Retry-After"]) >= 1
    assert request.call_count == 1


@pytest.mark.django_db
@override_settings(MICOMETEO_PLACE_SEARCH_REQUEST_INTERVAL=0)
def test_provider_retry_after_blocks_other_queries_but_keeps_cache_available() -> None:
    with patch(
        "place_search.provider._request",
        side_effect=PlaceSearchThrottled(retry_after=60),
    ) as provider_request:
        with pytest.raises(PlaceSearchThrottled):
            search_places(query="Abetone", language="it")

    with patch("place_search.provider._request", return_value={"features": []}) as provider_request:
        with pytest.raises(PlaceSearchThrottled):
            search_places(query="Femminamorta", language="it")
        assert provider_request.call_count == 0

    PlaceSearchCache.objects.create(
        normalized_query="pistoia",
        language="it",
        endpoint="https://photon.komoot.io/api",
        results=[{"name": "Pistoia"}],
        fetched_at=timezone.now(),
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    with patch("place_search.provider._request") as provider_request:
        results, cached = search_places(query="Pistoia", language="it")

    assert results == [{"name": "Pistoia"}]
    assert cached is True
    provider_request.assert_not_called()


def test_provider_retry_after_accepts_http_date() -> None:
    retry_at = timezone.now() + timedelta(seconds=30)
    value = format_datetime(retry_at, usegmt=True)

    assert 1 <= _retry_after(value) <= 31


def test_provider_rejects_malformed_json_response() -> None:
    class FakeResponse:
        status = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def getcode(self) -> int:
            return self.status

        def read(self) -> bytes:
            return b"not-json"

    def fake_urlopen(*, url: Request, timeout: float) -> FakeResponse:
        return FakeResponse()

    with patch("place_search.provider.urlopen", side_effect=fake_urlopen):
        with pytest.raises(PlaceSearchUnavailable):
            _request(query="Pistoia", language="it")


@pytest.mark.django_db
@override_settings(MICOMETEO_PLACE_SEARCH_REQUEST_INTERVAL=0)
def test_expired_place_search_cache_calls_provider_again() -> None:
    PlaceSearchCache.objects.create(
        normalized_query="abetone",
        language="it",
        endpoint="https://photon.komoot.io/api",
        results=[{"name": "Old Abetone"}],
        fetched_at=timezone.now() - timedelta(hours=2),
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    fresh = {"features": [_photon_feature(name="Abetone", longitude=10.66, latitude=44.13)]}

    with patch("place_search.provider._request", return_value=fresh) as request:
        results, cached = search_places(query="Abetone", language="it")

    assert results[0]["name"] == "Abetone"
    assert cached is False
    request.assert_called_once()


@pytest.mark.parametrize(("language", "provider_language"), [("it", "default"), ("en", "en")])
def test_provider_passes_a_request_object_and_timeout_to_urlopen(
    language: str, provider_language: str
) -> None:
    class FakeResponse:
        status = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def getcode(self) -> int:
            return self.status

        def read(self) -> bytes:
            return b'{"features": []}'

    def fake_urlopen(*, url: Request, timeout: float) -> FakeResponse:
        assert isinstance(url, Request)
        assert timeout == 4.0
        query = parse_qs(urlparse(url.full_url).query)
        assert query["q"] == ["Pistoia"]
        assert query["countrycode"] == ["IT"]
        assert query["layer"] == ["city", "locality", "district"]
        assert query["lang"] == [provider_language]
        return FakeResponse()

    with patch("place_search.provider.urlopen", side_effect=fake_urlopen):
        assert _request(query="Pistoia", language=language) == {"features": []}


def test_place_search_api_rejects_overlong_query() -> None:
    response = Client().get(path="/api/v1/places/search?q=" + "x" * 121)

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_query"


def test_place_resolve_rejects_invalid_coordinates() -> None:
    response = Client().post(
        path="/api/v1/places/resolve",
        data=json.dumps({"latitude": "not-a-number", "longitude": 10}),
        content_type="application/json",
    )

    assert response.status_code == 422


def test_place_resolve_reports_nonfinite_projection_as_outside_italy() -> None:
    with (
        patch("place_search.api._configured_forest_build", return_value=object()),
        patch("place_search.api.WGS84_TO_GRID.transform", return_value=(float("inf"), 0.0)),
    ):
        response = _resolve_post(client=Client(), latitude=0, longitude=0)

    assert response.status_code == 422
    assert response.json()["code"] == "outside_italy"


def test_place_resolve_distinguishes_configured_coverage_from_italy() -> None:
    build = SimpleNamespace(grid_build=object())
    region = SimpleNamespace(name="Toscana")
    with (
        patch("place_search.api._configured_forest_build", return_value=build),
        patch("place_search.api.GridRegion.objects.filter") as region_filter,
        patch("place_search.api.GridBuildCell.objects.select_related") as cell_manager,
    ):
        region_filter.return_value.order_by.return_value.first.return_value = region
        cell_manager.return_value.filter.return_value.order_by.return_value.first.return_value = None
        response = _resolve_post(client=Client(), latitude=43.9, longitude=10.9)

    assert response.status_code == 422
    assert response.json()["code"] == "outside_configured_coverage"


@pytest.mark.django_db
def test_place_resolve_covers_center_and_grid_edge_but_rejects_outside_point(
    resolve_geometry_fixture: dict[str, tuple[float, float] | str],
) -> None:
    with override_settings(MICOMETEO_FOREST_BUILD_VERSION=resolve_geometry_fixture["version"]):
        center_latitude, center_longitude = resolve_geometry_fixture["center"]
        client = Client()
        center_response = _resolve_post(
            client=client,
            latitude=center_latitude,
            longitude=center_longitude,
        )
        edge_latitude, edge_longitude = resolve_geometry_fixture["edge"]
        edge_response = _resolve_post(
            client=client,
            latitude=edge_latitude,
            longitude=edge_longitude,
        )
        outside_latitude, outside_longitude = resolve_geometry_fixture["outside"]
        outside_response = _resolve_post(
            client=client,
            latitude=outside_latitude,
            longitude=outside_longitude,
        )

    assert center_response.status_code == 200
    assert center_response.json()["square_id"] == resolve_geometry_fixture["square_id"]
    assert edge_response.status_code == 200
    assert edge_response.json()["square_id"] == resolve_geometry_fixture["square_id"]
    assert outside_response.status_code == 422
    assert outside_response.json()["code"] == "outside_italy"
    assert center_response["Cache-Control"] == "no-store"
