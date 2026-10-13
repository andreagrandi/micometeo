"""Application services for eligible cells, planning, accounting and checks."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from math import ceil
from pathlib import Path
from typing import Any, Callable, Sequence

from django.db.models import Q

from micometeo.weather.openmeteo import HOURLY_VARIABLES

from .eligibility import (
    WeatherCell,
    WeatherEligibilityError,
    canonical_cell_key,
    eligible_weather_cells,
    weather_cell,
    weather_cell_for_coordinates,
    weather_cell_key,
    weather_cells_for_forest_build,
    weather_cells_for_forest_cells,
)
from .planning import (
    DEFAULT_MODEL,
    MAX_LOCATIONS,
    RequestPlanningError,
    RequestSpec,
    build_request_spec,
    build_request_plan,
    canonical_request_digest,
    combine_request_specs,
    nominal_weight,
    plan_request,
    plan_cell_request_specs,
    plan_requests,
    reservation_weight,
    request_compatibility_key,
    quota_reservation_weight,
    required_dates,
)
from .provider import (
    CompletedRequestError,
    PendingRequestError,
    PermanentProviderError,
    ProviderError,
    ProviderResult,
    ResponseValidationError,
    WeatherProvider,
    fetch_reserved_weather,
    fetch_weather,
    get_or_create_request,
    request_spec_from_request,
)
from .quota import (
    LIMITS,
    QuotaCheck,
    ReservationResult,
    check_quota,
    finish_attempt,
    reserve_attempt,
)


# The windows below sit in summer so that no clock change touches them.
_BUDGET_DAY = date(2026, 6, 15)
_INITIAL_SPANS: tuple[tuple[int, int], ...] = (
    (-30, -18),
    (-17, -5),
    (-4, -1),
    (0, 7),
)
_REFRESH_SPANS: tuple[tuple[int, int], ...] = ((-1, -1), (0, 7))


def _sum_batch_weights(
    *,
    cell_count: int,
    spans: Sequence[tuple[int, int]],
    reserved: bool,
) -> Decimal:
    """Sum one canonical planner weight for every provider batch and date range."""
    if cell_count <= 0:
        return Decimal("0")
    result = Decimal("0")
    for first_offset, last_offset in spans:
        start_date = _BUDGET_DAY + timedelta(days=first_offset)
        end_date = _BUDGET_DAY + timedelta(days=last_offset)
        for offset in range(0, cell_count, MAX_LOCATIONS):
            places = min(MAX_LOCATIONS, cell_count - offset)
            if reserved:
                result += reservation_weight(
                    variables=len(HOURLY_VARIABLES),
                    start_date=start_date,
                    end_date=end_date,
                    places=places,
                )
            else:
                result += nominal_weight(
                    variables=len(HOURLY_VARIABLES),
                    days=(end_date - start_date).days + 1,
                    places=places,
                )
    return result


def _budget_weights(*, cell_count: int) -> dict[str, Decimal]:
    """Return initial, nightly and monthly weights for the 38-day window."""
    initial_nominal = _sum_batch_weights(cell_count=cell_count, spans=_INITIAL_SPANS, reserved=False)
    refresh_nominal = _sum_batch_weights(cell_count=cell_count, spans=_REFRESH_SPANS, reserved=False)
    initial_reserved = _sum_batch_weights(cell_count=cell_count, spans=_INITIAL_SPANS, reserved=True)
    refresh_reserved = _sum_batch_weights(cell_count=cell_count, spans=_REFRESH_SPANS, reserved=True)
    return {
        "initial_nominal": initial_nominal,
        "refresh_nominal": refresh_nominal,
        "initial_reserved": initial_reserved,
        "refresh_reserved": refresh_reserved,
        "steady_month_nominal": refresh_nominal * 31,
        "steady_month_reserved": refresh_reserved * 31,
        "first_month_nominal": initial_nominal + refresh_nominal * 30,
        "first_month_reserved": initial_reserved + refresh_reserved * 30,
    }


def _budget_http_requests(*, cell_count: int) -> dict[str, int]:
    """Return the HTTP requests of the initial load and one nightly refresh."""
    batch_count = ceil(cell_count / MAX_LOCATIONS) if cell_count else 0
    return {
        "initial_load": len(_INITIAL_SPANS) * batch_count,
        "nightly_refresh": len(_REFRESH_SPANS) * batch_count,
    }


def _month_budget(*, nominal: Decimal, reserved: Decimal) -> dict[str, Any]:
    """Return monthly weights together with the allowance and any overrun."""
    limit = LIMITS["month"]
    return {
        "nominal_weight": float(nominal),
        "reserved_weight": float(reserved),
        "month_limit": str(limit),
        "nominal_overrun": float(max(Decimal("0"), nominal - limit)),
        "reserved_overrun": float(max(Decimal("0"), reserved - limit)),
        "reserved_within_limit": reserved <= limit,
    }


def budget_for_forest_build(*, forest_build_version: str) -> dict[str, Any]:
    """Return a no-network budget from one completed forest build."""
    from national_forest.models import ForestBuild, ForestCell

    build = ForestBuild.objects.filter(version=forest_build_version).first()
    if build is None:
        raise WeatherEligibilityError(f"No forest build exists for {forest_build_version!r}.")
    if build.status != ForestBuild.Status.COMPLETED:
        raise WeatherEligibilityError(
            f"Forest build {forest_build_version!r} is {build.status}, not completed."
        )
    forest_cells = ForestCell.objects.filter(build=build, is_forest=True)
    if forest_cells.filter(
        Q(weather_latitude__isnull=True) | Q(weather_longitude__isnull=True)
    ).exists():
        raise WeatherEligibilityError("A forest square is missing its weather cell centre.")
    global_cells: set[str] = set()
    region_cells: dict[str, set[str]] = {}
    region_rows: dict[str, int] = {}
    region_names: dict[str, str] = {}
    rows = forest_cells.values_list(
        "grid_build_cell__owner_region__istat_code",
        "grid_build_cell__owner_region__name",
        "weather_latitude",
        "weather_longitude",
    ).iterator(chunk_size=10_000)
    forest_square_count = 0
    for code, name, latitude, longitude in rows:
        key = weather_cell(latitude=latitude, longitude=longitude).key
        global_cells.add(key)
        region_cells.setdefault(code, set()).add(key)
        region_rows[code] = region_rows.get(code, 0) + 1
        region_names[code] = name
        forest_square_count += 1
    cell_count = len(global_cells)
    batch_count = ceil(cell_count / MAX_LOCATIONS) if cell_count else 0
    weights = _budget_weights(cell_count=cell_count)
    return {
        "forest_build_version": forest_build_version,
        "national": {
            "forest_squares": forest_square_count,
            "distinct_weather_cells": cell_count,
            "batches_of_100": batch_count,
        },
        "regions": [
            {
                "istat_code": code,
                "name": region_names[code],
                "forest_squares": region_rows[code],
                "distinct_weather_cells": len(region_cells[code]),
            }
            for code in sorted(region_cells)
        ],
        "regional_cells_overlap": sum(len(values) for values in region_cells.values()) - cell_count,
        "regional_counts_are_not_additive": True,
        "window": "30 completed days, today and 7 forecast days, 38 dates",
        "counted_calls": {
            "nominal": {
                "initial_load": float(weights["initial_nominal"]),
                "nightly_refresh": float(weights["refresh_nominal"]),
            },
            "reserved": {
                "initial_load": float(weights["initial_reserved"]),
                "nightly_refresh": float(weights["refresh_reserved"]),
            },
        },
        "http_requests": _budget_http_requests(cell_count=cell_count),
        "monthly_usage": {
            "steady_month": _month_budget(
                nominal=weights["steady_month_nominal"],
                reserved=weights["steady_month_reserved"],
            ),
            "first_month": _month_budget(
                nominal=weights["first_month_nominal"],
                reserved=weights["first_month_reserved"],
            ),
        },
        "retries": {
            "one_retry_multiplier": 2,
            "steady_month_with_one_retry": float(weights["steady_month_reserved"] * 2),
            "first_month_with_one_retry": float(weights["first_month_reserved"] * 2),
        },
        "limits": {name: str(value) for name, value in LIMITS.items()},
        "policy": (
            "Reservations use every requested hourly timestamp through the closing Italian midnight, "
            "rounded up to provider day equivalents. The provider does not expose a returned billing weight."
        ),
    }


def check_weather_response(
    *,
    forest_build_version: str,
    assessment_date: date,
    limit: int = MAX_LOCATIONS,
    cache_dir: Path | None = None,
    transport: Callable[..., Any] | None = None,
    clock: Callable[..., Any] | None = None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Fetch at most one hundred eligible cells and return metadata only."""
    if limit <= 0 or limit > MAX_LOCATIONS:
        raise ValueError(f"The checked response must contain between one and {MAX_LOCATIONS} locations.")
    cells = eligible_weather_cells(forest_build_version=forest_build_version)[:limit]
    if not cells:
        raise WeatherEligibilityError("The completed forest build has no eligible weather cells.")
    spec = build_request_spec(
        locations=cells,
        assessment_date=assessment_date,
        model=model,
        forest_build_version=forest_build_version,
    )
    if spec is None:
        raise RequestPlanningError("The checked cells already have stored weather dates.")
    result = fetch_weather(spec=spec, transport=transport, clock=clock)
    destination = cache_dir or Path("data/raw/weather_requests")
    destination.mkdir(parents=True, exist_ok=True)
    output_path = destination / f"{spec.digest}.json"
    output_path.write_text(
        json.dumps(
            {
                "request": spec.as_dict(),
                "metadata": result.metadata,
                "attempt_ids": [str(value) for value in result.attempt_ids],
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "request_digest": spec.digest,
        "attempt_ids": [str(value) for value in result.attempt_ids],
        "metadata": result.metadata,
        "cache_path": str(output_path),
        "quota": result.quota.as_dict(),
    }


__all__ = [
    "CompletedRequestError",
    "LIMITS",
    "PendingRequestError",
    "PermanentProviderError",
    "ProviderError",
    "ProviderResult",
    "QuotaCheck",
    "RequestPlanningError",
    "RequestSpec",
    "ReservationResult",
    "ResponseValidationError",
    "WeatherCell",
    "WeatherEligibilityError",
    "WeatherProvider",
    "budget_for_forest_build",
    "build_request_spec",
    "build_request_plan",
    "canonical_cell_key",
    "canonical_request_digest",
    "combine_request_specs",
    "check_quota",
    "check_weather_response",
    "eligible_weather_cells",
    "fetch_weather",
    "fetch_reserved_weather",
    "finish_attempt",
    "get_or_create_request",
    "request_spec_from_request",
    "plan_request",
    "plan_cell_request_specs",
    "plan_requests",
    "required_dates",
    "request_compatibility_key",
    "reserve_attempt",
    "weather_cell",
    "weather_cell_for_coordinates",
    "weather_cell_key",
    "weather_cells_for_forest_build",
    "weather_cells_for_forest_cells",
    "quota_reservation_weight",
]
