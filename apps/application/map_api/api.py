"""Typed map metadata, forest layer and square read endpoints."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from django.conf import settings
from django.contrib.gis.db.models import Extent
from django.contrib.gis.db.models.functions import Transform
from django.contrib.gis.geos import GEOSGeometry
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from ninja import Router, Schema
from pyproj import Geod, Transformer
from shapely import transform
from shapely.geometry import mapping
from shapely.wkb import loads

from config.api_schemas import ApiErrorSchema
from estimate_updates.contracts import decode_result_bytes
from estimate_updates.models import EstimateResult, EstimateUpdate
from national_forest.layer import validate_layer
from national_forest.models import ForestBuild, ForestCell
from national_grid.models import GridBuildCell
from national_terrain.models import TerrainBuild
from weather_on_demand import services as weather_services
from weather_requests.eligibility import WeatherCell, weather_cell


WGS84_TO_GRID = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
GRID_TO_WGS84 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)
GEOD = Geod(ellps="WGS84")
MAX_VIEW_WIDTH_M = 60_000.0
MAX_VIEW_HEIGHT_M = 60_000.0
MAX_SQUARES = 16_000
MAX_DAYS_AHEAD = 7
MAP_CACHE_SECONDS = 300

_WEATHER_NOT_READY_REASONS: dict[str, tuple[str, str]] = {
    "fetch_pending": ("pending", "estimate.result_not_ready"),
    "fetch_running": ("pending", "estimate.result_not_ready"),
    "visitor_limit": ("visitor_limit", "estimate.visitor_limit"),
    "quota_exhausted": ("quota_exhausted", "estimate.quota_exhausted"),
    "provider_unavailable": ("provider_unavailable", "estimate.provider_unavailable"),
    "provider_refused": ("provider_refused", "estimate.provider_refused"),
}

router = Router(tags=["map"])


class CoverageSchema(Schema):
    """Describe the configured grid coverage in WGS84."""

    west: float
    south: float
    east: float
    north: float


class LayerInfoSchema(Schema):
    """Describe the immutable forest overview artifact."""

    url: str
    sha256: str
    gzip_bytes: int | None = None
    raw_bytes: int | None = None


class AttributionSchema(Schema):
    """Describe one map data source and its attribution."""

    name: str
    credit: str | None = None
    licence: str | None = None
    url: str | None = None


class WeatherCellSchema(Schema):
    """Describe the stored weather cell centre for one square."""

    latitude: float
    longitude: float


class InfoResponse(Schema):
    """Describe dates, coverage and limits for map reads."""

    today: date
    target_dates: list[date]
    coverage: CoverageSchema | None
    forest_build_version: str
    max_width_km: float
    max_height_km: float
    max_squares: int
    forest_layer: LayerInfoSchema
    attributions: list[AttributionSchema]


class SquarePropertiesSchema(Schema):
    """Describe one stored square result."""

    cell_id: str
    state: str
    percentage: int | None
    unavailable_reason: str | None
    reason: str | None
    target_date: date
    assessment_date: date | None
    update_id: UUID | None
    calculated_at: datetime | None
    message_key: str
    weather_cell: WeatherCellSchema | None


class SquareFeatureSchema(Schema):
    """Describe one GeoJSON square feature."""

    type: Literal["Feature"]
    id: str
    geometry: dict[str, Any]
    properties: SquarePropertiesSchema


class SquaresResponse(Schema):
    """Describe one GeoJSON square collection."""

    type: Literal["FeatureCollection"]
    target_date: date
    square_count: int
    features: list[SquareFeatureSchema]


def _today() -> date:
    """Return today's date at the Europe/Rome boundary."""
    return weather_services.italian_assessment_date()


def _error_response(
    *,
    status: int,
    code: str,
    message: str,
    message_key: str,
    details: dict[str, Any] | None = None,
) -> JsonResponse:
    """Build one stable JSON error response."""
    return JsonResponse(
        {
            "code": code,
            "message": message,
            "message_key": message_key,
            "details": details,
        },
        status=status,
    )


def _configured_build() -> ForestBuild | None:
    """Return the configured completed forest build."""
    version = str(getattr(settings, "MICOMETEO_FOREST_BUILD_VERSION", ""))
    if not version:
        return None
    return (
        ForestBuild.objects.select_related("grid_build")
        .filter(
            version=version,
            status=ForestBuild.Status.COMPLETED,
        )
        .first()
    )


def _configured_terrain(*, grid_build_id: UUID) -> TerrainBuild | None:
    """Return the configured completed terrain build for one grid."""
    version = str(getattr(settings, "MICOMETEO_TERRAIN_BUILD_VERSION", ""))
    if not version:
        return None
    return TerrainBuild.objects.filter(
        version=version,
        status=TerrainBuild.Status.COMPLETED,
        grid_build_id=grid_build_id,
    ).first()


def _source_text(*, value: object) -> str | None:
    """Return one non-empty stored source value."""
    return value if isinstance(value, str) and value else None


def _attributions(*, build: ForestBuild) -> list[AttributionSchema]:
    """Return ordered attributions from the configured build records."""
    grid_metadata = dict(build.grid_build.source_metadata or {})
    attributions = [
        AttributionSchema(
            name="ISTAT boundaries",
            credit=_source_text(value=grid_metadata.get("credit")),
            licence=_source_text(value=grid_metadata.get("license")),
            url=_source_text(value=grid_metadata.get("license_url")),
        ),
        AttributionSchema(
            name="Copernicus forest",
            credit=build.credit or None,
            licence=build.licence or None,
            url=build.catalogue_url or None,
        ),
    ]
    terrain = _configured_terrain(grid_build_id=build.grid_build_id)
    if terrain is not None:
        terrain_metadata = dict(terrain.source_metadata or {})
        terrain_credit = _source_text(value=terrain_metadata.get("credit"))
        attributions.append(
            AttributionSchema(
                name="Copernicus terrain",
                credit=terrain_credit,
                licence=terrain_credit,
                url=_source_text(
                    value=terrain_metadata.get("source_dataset")
                    or terrain_metadata.get("source_url")
                ),
            )
        )
    attributions.append(
        AttributionSchema(
            name="Open-Meteo",
            credit="Weather data by Open-Meteo.com",
            licence="CC BY 4.0",
            url="https://open-meteo.com/",
        )
    )
    return attributions


def _build_error(*, status: int = 503) -> JsonResponse:
    """Return the stable response for unavailable configured data."""
    return _error_response(
        status=status,
        code="forest_build_unavailable",
        message="The configured completed forest build is not available.",
        message_key="map.forest_build_unavailable",
    )


def _parse_date(value: str | None) -> tuple[date | None, JsonResponse | None]:
    if not value:
        return None, _error_response(
            status=400,
            code="missing_parameter",
            message="The parameter target_date is required.",
            message_key="map.target_date_required",
            details={"parameter": "target_date"},
        )
    if len(value) != 10:
        return None, _error_response(
            status=400,
            code="invalid_date",
            message="The parameter target_date must look like 2026-10-12.",
            message_key="map.invalid_date",
        )
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None, _error_response(
            status=400,
            code="invalid_date",
            message="The parameter target_date is not a real date.",
            message_key="map.invalid_date",
        )
    if parsed.isoformat() != value:
        return None, _error_response(
            status=400,
            code="invalid_date",
            message="The parameter target_date must look like 2026-10-12.",
            message_key="map.invalid_date",
        )
    return parsed, None


def _parse_bbox(
    value: str | None,
) -> tuple[tuple[float, float, float, float] | None, JsonResponse | None]:
    message = "The parameter bbox must be four finite WGS84 numbers: west,south,east,north."
    if not value:
        return None, _error_response(
            status=400,
            code="missing_parameter",
            message="The parameter bbox is required.",
            message_key="map.bbox_required",
            details={"parameter": "bbox"},
        )
    parts = value.split(",")
    if len(parts) != 4:
        return None, _error_response(
            status=400,
            code="invalid_bbox",
            message=message,
            message_key="map.invalid_bbox",
        )
    try:
        parsed = tuple(float(part.strip()) for part in parts)
    except (TypeError, ValueError):
        return None, _error_response(
            status=400,
            code="invalid_bbox",
            message=message,
            message_key="map.invalid_bbox",
        )
    west, south, east, north = parsed
    if (
        not all(math.isfinite(number) for number in parsed)
        or not -180 <= west <= 180
        or not -180 <= east <= 180
        or not -90 <= south <= 90
        or not -90 <= north <= 90
    ):
        return None, _error_response(
            status=400,
            code="invalid_bbox",
            message="The bbox coordinates must be finite WGS84 values within longitude and latitude bounds.",
            message_key="map.invalid_bbox",
        )
    if west >= east or south >= north:
        return None, _error_response(
            status=400,
            code="invalid_bbox",
            message="The bbox needs west smaller than east and south smaller than north.",
            message_key="map.invalid_bbox_order",
        )
    return (west, south, east, north), None


def _bbox_geometry(*, bbox: tuple[float, float, float, float]) -> GEOSGeometry:
    """Transform a WGS84 box into the stored grid CRS."""
    west, south, east, north = bbox
    corners = [
        WGS84_TO_GRID.transform(west, south),
        WGS84_TO_GRID.transform(east, south),
        WGS84_TO_GRID.transform(east, north),
        WGS84_TO_GRID.transform(west, north),
        WGS84_TO_GRID.transform(west, south),
    ]
    geometry = GEOSGeometry(
        json.dumps({"type": "Polygon", "coordinates": [[list(point) for point in corners]]})
    )
    geometry.srid = 3035
    return geometry


def _bbox_size_m(*, bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    west, south, east, north = bbox
    _, _, width = GEOD.inv(west, south, east, south)
    _, _, height = GEOD.inv(west, south, west, north)
    return abs(width), abs(height)


@lru_cache(maxsize=32)
def _coverage_cached(*, grid_build_id: str, forest_fingerprint: str) -> CoverageSchema | None:
    """Return one immutable grid extent in WGS84 from its stored geometries."""
    extent = (
        GridBuildCell.objects.filter(build_id=grid_build_id)
        .annotate(wgs84_geometry=Transform("cell__geometry", srid=4326))
        .aggregate(wgs84_extent=Extent("wgs84_geometry"))
        .get("wgs84_extent")
    )
    del forest_fingerprint
    if extent is None:
        return None
    west, south, east, north = extent
    return CoverageSchema(
        west=float(west),
        south=float(south),
        east=float(east),
        north=float(north),
    )


def _coverage(*, build: ForestBuild) -> CoverageSchema | None:
    """Return the configured build's actual transformed geometry extent."""
    return _coverage_cached(
        grid_build_id=str(build.grid_build_id),
        forest_fingerprint=build.fingerprint,
    )


def _layer_info(*, build: ForestBuild) -> LayerInfoSchema:
    return LayerInfoSchema(
        url="/api/v1/forest-layer",
        sha256=build.layer_sha256,
        gzip_bytes=build.layer_gzip_bytes,
        raw_bytes=build.layer_raw_bytes,
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _square_properties(
    *,
    cell_id: str,
    state: str,
    percentage: int | None,
    reason: str | None,
    target_date: date,
    assessment_date: date | None,
    update_id: UUID | str | None,
    calculated_at: datetime | None,
    message_key: str,
    weather_cell_coordinates: dict[str, float] | None,
) -> dict[str, Any]:
    """Return the stable public properties for one square."""
    public_update_id = str(update_id) if update_id is not None else None
    return {
        "cell_id": cell_id,
        "state": state,
        "percentage": percentage,
        "unavailable_reason": reason,
        "reason": reason,
        "target_date": target_date.isoformat(),
        "assessment_date": _json_value(assessment_date),
        "update_id": public_update_id,
        "calculated_at": _json_value(calculated_at),
        "message_key": message_key,
        "weather_cell": weather_cell_coordinates,
    }


def _weather_cell_coordinates(*, cell: ForestCell) -> dict[str, float] | None:
    """Return the stored weather cell centre when both coordinates exist."""
    if cell.weather_latitude is None or cell.weather_longitude is None:
        return None
    return {
        "latitude": float(cell.weather_latitude),
        "longitude": float(cell.weather_longitude),
    }


def _geometry_wgs84(cell: ForestCell) -> dict[str, Any]:
    geometry = loads(bytes(cell.grid_build_cell.cell.geometry.wkb))
    transformed = transform(geometry, GRID_TO_WGS84.transform, interleaved=False)
    return mapping(transformed)


def _weather_cells(*, cells: list[ForestCell]) -> tuple[WeatherCell, ...]:
    values: dict[str, WeatherCell] = {}
    for cell in cells:
        if cell.is_forest is not True:
            continue
        if cell.weather_latitude is None or cell.weather_longitude is None:
            continue
        value = weather_cell(latitude=cell.weather_latitude, longitude=cell.weather_longitude)
        values[value.key] = value
    return tuple(values[key] for key in sorted(values))


def _cache_key(
    *,
    build_version: str,
    bbox: tuple[float, float, float, float],
    target_date: date,
    weather_items: tuple[tuple[str, str, str | None, str | None, str | None], ...],
) -> str:
    normalized_bbox = ",".join(format(value, ".12g") for value in bbox)
    identity = {
        "forest_build_version": build_version,
        "bbox": normalized_bbox,
        "target_date": target_date.isoformat(),
        "weather": weather_items,
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"micometeo-map-v2:{digest}"


def _weather_identity(
    *,
    cells: tuple[WeatherCell, ...],
    by_cell: dict[str, Any],
    updates: dict[tuple[str, str], EstimateUpdate],
) -> tuple[tuple[str, str, str | None, str | None, str | None], ...]:
    values: list[tuple[str, str, str | None, str | None, str | None]] = []
    for cell in cells:
        result = by_cell.get(cell.key)
        state = str(getattr(result, "state", "not_available_yet"))
        reason_code = getattr(result, "reason_code", None)
        reason_text = str(reason_code) if reason_code is not None else None
        snapshot_id = getattr(result, "snapshot_id", None)
        snapshot_text = str(snapshot_id) if snapshot_id is not None else None
        update = updates.get((snapshot_text or "", cell.key))
        marker = str(update.public_id) if update is not None else "pending"
        values.append((cell.key, state, snapshot_text, marker, reason_text))
    return tuple(values)


def _weather_not_ready_properties(*, weather_result: Any) -> tuple[str, str]:
    """Return the public reason and message key for a missing weather result."""
    reason_code = str(getattr(weather_result, "reason_code", ""))
    return _WEATHER_NOT_READY_REASONS.get(
        reason_code,
        ("pending", "estimate.result_not_ready"),
    )


def _squares_response(*, body: dict[str, Any], key: str) -> JsonResponse:
    """Build a cached response for one stable square result."""
    response = JsonResponse(body)
    response["Cache-Control"] = "no-cache"
    response["Vary"] = "Accept-Encoding"
    response["ETag"] = f'"{hashlib.sha256(key.encode("utf-8")).hexdigest()}"'
    return response


def _result_properties(
    *,
    cell: ForestCell,
    target_date: date,
    weather_result: Any,
    update: EstimateUpdate | None,
    estimate_result: EstimateResult | None,
) -> dict[str, Any]:
    """Resolve one stored row from bulk identities and bytes."""
    cell_id = cell.grid_build_cell.cell.cell_id
    weather_cell_coordinates = _weather_cell_coordinates(cell=cell)
    if cell.is_forest is None or cell.forest_share is None:
        return _square_properties(
            cell_id=cell_id,
            state="unavailable",
            percentage=None,
            reason="missing_forest_data",
            target_date=target_date,
            assessment_date=None,
            update_id=None,
            calculated_at=None,
            message_key="estimate.missing_forest",
            weather_cell_coordinates=weather_cell_coordinates,
        )
    if cell.is_forest is False or cell.forest_share < 0.1:
        return _square_properties(
            cell_id=cell_id,
            state="noforest",
            percentage=None,
            reason="noforest",
            target_date=target_date,
            assessment_date=None,
            update_id=None,
            calculated_at=None,
            message_key="estimate.no_forest",
            weather_cell_coordinates=weather_cell_coordinates,
        )

    state = str(getattr(weather_result, "state", "not_available_yet"))
    assessment_date = getattr(weather_result, "assessment_date", None)
    if update is not None:
        assessment_date = update.assessment_date
    if update is None:
        if assessment_date is not None and (target_date - assessment_date).days > MAX_DAYS_AHEAD:
            state = "expired"
            reason = "target_outside_update_range"
            message_key = "estimate.target_outside_update_range"
        elif state == "not_available_yet":
            state = "noresultyet"
            reason, message_key = _weather_not_ready_properties(weather_result=weather_result)
        else:
            state = "noresultyet"
            reason = "pending"
            message_key = "estimate.result_not_ready"
        return _square_properties(
            cell_id=cell_id,
            state=state,
            percentage=None,
            reason=reason,
            target_date=target_date,
            assessment_date=assessment_date,
            update_id=None,
            calculated_at=None,
            message_key=message_key,
            weather_cell_coordinates=weather_cell_coordinates,
        )
    offset = (target_date - update.assessment_date).days
    if offset < 0 or offset > MAX_DAYS_AHEAD or estimate_result is None:
        return _square_properties(
            cell_id=cell_id,
            state="expired" if offset < 0 or offset > MAX_DAYS_AHEAD else "noresultyet",
            percentage=None,
            reason=("target_outside_update_range" if offset < 0 or offset > MAX_DAYS_AHEAD else "pending"),
            target_date=target_date,
            assessment_date=update.assessment_date,
            update_id=update.public_id,
            calculated_at=update.calculated_at,
            message_key=(
                "estimate.target_outside_update_range"
                if offset < 0 or offset > MAX_DAYS_AHEAD
                else "estimate.result_not_ready"
            ),
            weather_cell_coordinates=weather_cell_coordinates,
        )
    try:
        decoded = decode_result_bytes(values=estimate_result.values)
        value = decoded[offset]
    except (IndexError, ValueError):
        return _square_properties(
            cell_id=cell_id,
            state="unavailable",
            percentage=None,
            reason="requiredgap",
            target_date=target_date,
            assessment_date=update.assessment_date,
            update_id=update.public_id,
            calculated_at=update.calculated_at,
            message_key="estimate.required_gap",
            weather_cell_coordinates=weather_cell_coordinates,
        )
    if isinstance(value, int):
        return _square_properties(
            cell_id=cell_id,
            state="available",
            percentage=value,
            reason=None,
            target_date=target_date,
            assessment_date=update.assessment_date,
            update_id=update.public_id,
            calculated_at=update.calculated_at,
            message_key="estimate.available",
            weather_cell_coordinates=weather_cell_coordinates,
        )
    return _square_properties(
        cell_id=cell_id,
        state="unavailable",
        percentage=None,
        reason=value,
        target_date=target_date,
        assessment_date=update.assessment_date,
        update_id=update.public_id,
        calculated_at=update.calculated_at,
        message_key="estimate.unavailable",
        weather_cell_coordinates=weather_cell_coordinates,
    )


@router.get("/info", response={200: InfoResponse, 503: ApiErrorSchema})
def info(request: HttpRequest) -> InfoResponse | HttpResponse:
    """Return the dates, coverage and limits for configured map data."""
    del request
    build = _configured_build()
    if build is None:
        return _build_error()
    today = _today()
    dates = [today + timedelta(days=offset) for offset in range(MAX_DAYS_AHEAD + 1)]
    coverage = _coverage(build=build)
    return {
        "today": today.isoformat(),
        "target_dates": [value.isoformat() for value in dates],
        "coverage": coverage.dict() if coverage is not None else None,
        "forest_build_version": build.version,
        "max_width_km": MAX_VIEW_WIDTH_M / 1_000,
        "max_height_km": MAX_VIEW_HEIGHT_M / 1_000,
        "max_squares": MAX_SQUARES,
        "forest_layer": _layer_info(build=build).dict(),
        "attributions": [attribution.dict() for attribution in _attributions(build=build)],
    }


def _layer_error() -> JsonResponse:
    """Return the stable response for an unavailable forest layer."""
    return _error_response(
        status=503,
        code="forest_layer_unavailable",
        message="The configured forest layer artifact is not available.",
        message_key="map.forest_layer_unavailable",
    )


def _read_layer(*, build: ForestBuild) -> tuple[bytes, str] | JsonResponse:
    """Read and verify the immutable forest layer artifact."""
    if not build.layer_path or not build.layer_sha256:
        return _layer_error()
    path = Path(build.layer_path)
    try:
        compressed = path.read_bytes()
        digest = hashlib.sha256(compressed).hexdigest()
        if digest != build.layer_sha256:
            raise ValueError("The forest layer hash does not match its build record.")
        validate_layer(path=path)
        raw = gzip.decompress(compressed)
        if build.layer_gzip_bytes is not None and len(compressed) != build.layer_gzip_bytes:
            raise ValueError("The forest layer size does not match its build record.")
        if build.layer_raw_bytes is not None and len(raw) != build.layer_raw_bytes:
            raise ValueError("The forest layer raw size does not match its build record.")
    except (OSError, EOFError, ValueError, gzip.BadGzipFile):
        return _layer_error()
    return compressed, digest


@router.get("/forest-layer", response={200: Any, 503: ApiErrorSchema})
def forest_layer(request: HttpRequest) -> HttpResponse:
    """Return the verified immutable gzip forest overview layer."""
    build = _configured_build()
    if build is None:
        return _build_error()
    layer = _read_layer(build=build)
    if isinstance(layer, JsonResponse):
        return layer
    compressed, digest = layer
    accepts_gzip = "gzip" in request.META.get("HTTP_ACCEPT_ENCODING", "").lower()
    etag = f'"{digest}"'
    if request.META.get("HTTP_IF_NONE_MATCH") == etag:
        response = HttpResponse(status=304)
        response["ETag"] = etag
        response["Cache-Control"] = "no-cache"
        response["Vary"] = "Accept-Encoding"
        return response
    content = compressed if accepts_gzip else gzip.decompress(compressed)
    response = HttpResponse(content=content, content_type="application/geo+json")
    response["ETag"] = etag
    response["Cache-Control"] = "no-cache"
    response["Vary"] = "Accept-Encoding"
    if accepts_gzip:
        response["Content-Encoding"] = "gzip"
    return response


@router.get(
    "/squares",
    response={200: SquaresResponse, 400: ApiErrorSchema, 503: ApiErrorSchema},
    openapi_extra={
        "parameters": [
            {
                "in": "query",
                "name": "bbox",
                "required": True,
                "description": "WGS84 west,south,east,north bounds.",
                "schema": {"type": "string", "minLength": 1},
            },
            {
                "in": "query",
                "name": "target_date",
                "required": True,
                "description": "Italian calendar date in YYYY-MM-DD form.",
                "schema": {
                    "type": "string",
                    "format": "date",
                    "pattern": r"^\d{4}-\d{2}-\d{2}$",
                },
            },
        ]
    },
)
def squares(request: HttpRequest) -> HttpResponse:
    """Return exact stored estimate values for the requested map view."""
    bbox = request.GET.get("bbox")
    target_date = request.GET.get("target_date")
    parsed_bbox, bbox_error = _parse_bbox(bbox)
    if bbox_error is not None or parsed_bbox is None:
        return bbox_error or _error_response(
            status=400,
            code="invalid_bbox",
            message="The bbox is invalid.",
            message_key="map.invalid_bbox",
        )
    parsed_date, date_error = _parse_date(target_date)
    if date_error is not None or parsed_date is None:
        return date_error or _error_response(
            status=400,
            code="invalid_date",
            message="The target date is invalid.",
            message_key="map.invalid_date",
        )
    today = _today()
    available_dates = [today + timedelta(days=offset) for offset in range(MAX_DAYS_AHEAD + 1)]
    if parsed_date not in available_dates:
        return _error_response(
            status=400,
            code="unsupported_date",
            message=(
                f"The target_date must be from {available_dates[0].isoformat()} "
                f"through {available_dates[-1].isoformat()}."
            ),
            message_key="map.unsupported_date",
            details={"available_dates": [value.isoformat() for value in available_dates]},
        )
    width_m, height_m = _bbox_size_m(bbox=parsed_bbox)
    if width_m > MAX_VIEW_WIDTH_M or height_m > MAX_VIEW_HEIGHT_M:
        return _error_response(
            status=400,
            code="view_too_large",
            message="Zoom in for estimates before requesting this view.",
            message_key="map.zoom_in_for_estimates",
            details={
                "width_m": round(width_m, 2),
                "height_m": round(height_m, 2),
                "max_width_m": MAX_VIEW_WIDTH_M,
                "max_height_m": MAX_VIEW_HEIGHT_M,
            },
        )
    build = _configured_build()
    if build is None:
        return _build_error()
    geometry = _bbox_geometry(bbox=parsed_bbox)
    cells = list(
        ForestCell.objects.select_related("grid_build_cell__cell")
        .filter(
            build_id=build.id,
            grid_build_cell__cell__geometry__intersects=geometry,
        )
        .order_by("grid_build_cell__cell__cell_id")
    )
    if not cells:
        return _error_response(
            status=400,
            code="outside_coverage",
            message="The bbox is outside the configured grid coverage.",
            message_key="map.outside_coverage",
        )
    if len(cells) > MAX_SQUARES:
        return _error_response(
            status=400,
            code="square_limit_exceeded",
            message="Zoom in for estimates before requesting this many squares.",
            message_key="map.square_limit_exceeded",
            details={"square_count": len(cells), "max_squares": MAX_SQUARES},
        )
    eligible_cells = _weather_cells(cells=cells)
    lookup = None
    if eligible_cells:
        lookup = weather_services.request_weather(
            cells=eligible_cells,
            visitor_id=request.META.get("REMOTE_ADDR"),
            assessment_date=today,
            wait_seconds=3,
            forest_build_version=build.version,
        )
    by_cell = dict(getattr(lookup, "by_cell", {}) if lookup is not None else {})
    snapshot_ids = [
        str(getattr(by_cell.get(cell.key), "snapshot_id"))
        for cell in eligible_cells
        if getattr(by_cell.get(cell.key), "snapshot_id", None) is not None
    ]
    updates = list(
        EstimateUpdate.objects.filter(
            forest_build_id=build.id,
            snapshot_id__in=snapshot_ids,
        ).order_by("-calculated_at", "-id")
    ) if snapshot_ids else []
    updates_by_key: dict[tuple[str, str], EstimateUpdate] = {}
    for update in updates:
        updates_by_key.setdefault((str(update.snapshot_id), update.cell_key), update)
    update_ids = [update.id for update in updates]
    forest_cell_ids = [cell.id for cell in cells]
    estimate_rows = list(
        EstimateResult.objects.filter(
            update_id__in=update_ids,
            forest_cell_id__in=forest_cell_ids,
        )
    ) if update_ids else []
    estimate_by_key = {(row.update_id, row.forest_cell_id): row for row in estimate_rows}
    weather_identity = _weather_identity(
        cells=eligible_cells,
        by_cell=by_cell,
        updates=updates_by_key,
    )
    key = _cache_key(
        build_version=build.version,
        bbox=parsed_bbox,
        target_date=parsed_date,
        weather_items=weather_identity,
    )
    cached = cache.get(key)
    if cached is not None:
        return _squares_response(body=cached, key=key)

    features: list[dict[str, Any]] = []
    for cell in cells:
        cell_key = None
        if cell.is_forest is True and cell.weather_latitude is not None and cell.weather_longitude is not None:
            cell_key = weather_cell(
                latitude=cell.weather_latitude,
                longitude=cell.weather_longitude,
            ).key
        weather_result = by_cell.get(cell_key) if cell_key is not None else None
        snapshot_id = str(getattr(weather_result, "snapshot_id", "")) if weather_result else ""
        update = updates_by_key.get((snapshot_id, cell_key or ""))
        estimate = estimate_by_key.get((update.id, cell.id)) if update is not None else None
        properties = _result_properties(
            cell=cell,
            target_date=parsed_date,
            weather_result=weather_result,
            update=update,
            estimate_result=estimate,
        )
        features.append(
            {
                "type": "Feature",
                "id": cell.grid_build_cell.cell.cell_id,
                "geometry": _geometry_wgs84(cell),
                "properties": properties,
            }
        )
    body = {
        "type": "FeatureCollection",
        "target_date": parsed_date.isoformat(),
        "square_count": len(features),
        "features": features,
    }
    cache.set(key, body, timeout=MAP_CACHE_SECONDS)
    return _squares_response(body=body, key=key)


__all__ = [
    "InfoResponse",
    "SquaresResponse",
    "forest_layer",
    "info",
    "router",
    "squares",
]
