from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import Page, Route, expect


TARGET_DATES = tuple(f"2026-10-{day:02d}" for day in range(12, 20))
TRANSPARENT_TILE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _polygon(center_x: float, center_y: float, size: float = 0.002) -> list[list[list[float]]]:
    return [
        [
            [center_x - size, center_y - size],
            [center_x + size, center_y - size],
            [center_x + size, center_y + size],
            [center_x - size, center_y + size],
            [center_x - size, center_y - size],
        ]
    ]


def _feature(
    *,
    cell_id: str,
    center_x: float,
    center_y: float,
    state: str,
    percentage: int | None,
    reason: str | None = None,
    target_date: str = "2026-10-12",
    assessment_date: str = "2026-10-12",
    update_id: str | None = "update-current",
) -> dict[str, object]:
    properties = {
        "cell_id": cell_id,
        "state": state,
        "percentage": percentage,
        "unavailable_reason": reason,
        "reason": reason,
        "target_date": target_date,
        "assessment_date": assessment_date,
        "update_id": update_id,
        "calculated_at": "2026-10-12T08:30:00Z",
        "message_key": "estimate.available" if state == "available" else None,
        "weather_cell": (
            {"latitude": round(center_y, 2), "longitude": round(center_x, 2)}
            if state not in {"noforest", "unavailable", "expired"}
            else None
        ),
    }
    return {
        "type": "Feature",
        "id": cell_id,
        "geometry": {
            "type": "Polygon",
            "coordinates": _polygon(center_x=center_x, center_y=center_y),
        },
        "properties": properties,
    }


def _squares_response(target_date: str) -> dict[str, object]:
    assessment_date = "2026-10-11" if target_date == "2026-10-15" else "2026-10-12"
    return {
        "type": "FeatureCollection",
        "target_date": target_date,
        "square_count": 6,
        "features": [
            _feature(
                cell_id="cell-zero",
                center_x=10.640,
                center_y=44.130,
                state="available",
                percentage=0,
                target_date=target_date,
                assessment_date=assessment_date,
            ),
            _feature(
                cell_id="cell-hundred",
                center_x=10.645,
                center_y=44.130,
                state="available",
                percentage=100,
                target_date=target_date,
                assessment_date="2026-10-12" if target_date == "2026-10-15" else assessment_date,
            ),
            _feature(
                cell_id="cell-missing",
                center_x=10.650,
                center_y=44.130,
                state="unavailable",
                percentage=None,
                reason="missing_forest_data",
                update_id=None,
                target_date=target_date,
                assessment_date=assessment_date,
            ),
            _feature(
                cell_id="cell-noforest",
                center_x=10.655,
                center_y=44.130,
                state="noforest",
                percentage=None,
                reason="noforest",
                update_id=None,
                target_date=target_date,
                assessment_date=assessment_date,
            ),
            _feature(
                cell_id="cell-pending",
                center_x=10.660,
                center_y=44.130,
                state="noresultyet",
                percentage=None,
                reason="pending",
                update_id=None,
                target_date=target_date,
                assessment_date=assessment_date,
            ),
            _feature(
                cell_id="cell-expired",
                center_x=10.665,
                center_y=44.130,
                state="expired",
                percentage=None,
                reason="update_expired",
                update_id=None,
                target_date=target_date,
                assessment_date=assessment_date,
            ),
        ],
    }


def _pending_squares_response(target_date: str) -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "target_date": target_date,
        "square_count": 1,
        "features": [
            _feature(
                cell_id="cell-pending",
                center_x=10.650,
                center_y=44.130,
                state="noresultyet",
                percentage=None,
                reason="pending",
                update_id=None,
                target_date=target_date,
            )
        ],
    }


def _info_response() -> dict[str, object]:
    return {
        "today": TARGET_DATES[0],
        "target_dates": list(TARGET_DATES),
        "coverage": {"west": -1.0, "south": -1.0, "east": 12.0, "north": 46.0},
        "max_width_km": 60,
        "max_height_km": 60,
        "max_squares": 16_000,
        "forest_build_version": "browser-fixture-forest-v1",
        "forest_layer": {
            "url": "/api/v1/forest-layer",
            "sha256": "0" * 64,
            "compressed_size": 128,
            "uncompressed_size": 512,
        },
        "attributions": [
            {
                "name": "OpenStreetMap",
                "credit": "OpenStreetMap contributors",
                "licence": "ODbL",
                "url": "https://www.openstreetmap.org/copyright",
            },
            {
                "name": "Open-Meteo",
                "credit": "Weather data by Open-Meteo.com",
                "licence": "CC BY 4.0",
                "url": "https://open-meteo.com/",
            },
        ],
    }


def _forest_response() -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "forest-area",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": _polygon(center_x=10.65, center_y=44.14, size=0.09),
                },
                "properties": {"forest_share": 0.68},
            },
            {
                "type": "Feature",
                "id": "open-area",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": _polygon(center_x=10.82, center_y=44.30, size=0.02),
                },
                "properties": {"forest_share": 0.0},
            },
        ],
    }


def _area_response(*, cell_id: str, target_date: str, update_id: str) -> dict[str, object]:
    feature = next(
        item for item in _squares_response(target_date)["features"]
        if item["properties"]["cell_id"] == cell_id
    )
    properties = feature["properties"]
    return {
        "selection": {
            "square_id": cell_id,
            "geometry": feature["geometry"],
            "bounds": {"west": 10.63, "south": 44.12, "east": 10.65, "north": 44.14},
            "centroid": {"latitude": 44.13, "longitude": 10.64},
            "representative_coordinates": {"latitude": 44.13, "longitude": 10.64},
            "target_date": target_date,
            "assessment_date": properties["assessment_date"],
            "days_ahead": 0,
            "update_id": update_id,
        },
        "estimate": {
            "state": "available",
            "whole_percentage": properties["percentage"],
            "unavailable_reason": None,
            "calculated_at": properties["calculated_at"],
            "method_version": "fixture-v1",
            "experimental_unvalidated": True,
            "experimental_explanation_key": "estimate.experimental_unvalidated",
            "translation_key": "estimate.available",
        },
        "facts": [],
        "weather": {},
        "sources": {},
    }


def _background_style(*, contrast: bool) -> dict[str, object]:
    return {
        "version": 8,
        "name": "Micometeo browser fixture",
        "sources": {
            "osm": {
                "type": "raster",
                "tiles": ["https://tiles.openfreemap.org/fixture/{z}/{x}/{y}.png"],
                "tileSize": 256,
                "attribution": "OpenStreetMap contributors",
            }
        },
        "layers": [
            {
                "id": "osm-background",
                "type": "raster",
                "source": "osm",
                "paint": {
                    "raster-brightness-min": 0.35 if contrast else 0.0,
                    "raster-brightness-max": 0.85 if contrast else 1.0,
                },
            }
        ],
    }


def _install_map_routes(
    page: Page,
    *,
    fail_first_squares_request: bool = False,
    fail_first_area_request: bool = False,
    fail_area_target_date: str | None = None,
    pending_squares: bool = False,
    unique_calculated_times: bool = False,
) -> list[dict[str, object]]:
    requests: list[dict[str, object]] = []
    failed_squares_request = False
    failed_area_request = False

    def fulfill_json(route: Route, body: dict[str, object], *, status: int = 200) -> None:
        route.fulfill(
            status=status,
            content_type="application/json",
            body=json.dumps(body),
        )

    def api_route(route: Route) -> None:
        nonlocal failed_area_request, failed_squares_request
        request = route.request
        parsed = urlparse(request.url)
        query = parse_qs(parsed.query)
        requests.append(
            {
                "path": parsed.path,
                "query": query,
                "url": request.url,
            }
        )
        if parsed.path.endswith("/info"):
            fulfill_json(route, _info_response())
            return
        if parsed.path.endswith("/forest-layer"):
            fulfill_json(route, _forest_response())
            return
        if parsed.path.endswith("/estimate-overview"):
            target_date = query.get("target_date", [TARGET_DATES[0]])[0]
            feature = _feature(cell_id="overview-test", center_x=10.65, center_y=44.14,
                               state="available", percentage=80, target_date=target_date)
            feature["geometry"]["coordinates"] = _polygon(10.65, 44.14, 0.1)
            feature["properties"]["overview"] = True
            fulfill_json(route, {"type": "FeatureCollection", "target_date": target_date, "features": [feature]})
            return
        if "/areas/" in parsed.path:
            cell_id = parsed.path.rsplit("/", 1)[-1]
            target_date = query.get("target_date", [TARGET_DATES[0]])[0]
            update_id = query.get("update_id", [""])[0]
            if (
                fail_first_area_request
                and not failed_area_request
                and (not fail_area_target_date or target_date == fail_area_target_date)
            ):
                failed_area_request = True
                fulfill_json(
                    route,
                    {"code": "provider_unavailable", "message": "The area estimate is temporarily unavailable."},
                    status=503,
                )
                return
            if target_date > "2026-10-18":
                fulfill_json(
                    route,
                    {"estimate": {"whole_percentage": None}},
                )
                return
            fulfill_json(route, _area_response(cell_id=cell_id, target_date=target_date, update_id=update_id))
            return
        if parsed.path.endswith("/squares"):
            target_date = query.get("target_date", [TARGET_DATES[0]])[0]
            if (
                fail_first_squares_request
                and target_date != TARGET_DATES[0]
                and not failed_squares_request
            ):
                failed_squares_request = True
                fulfill_json(
                    route,
                    {
                        "code": "provider_unavailable",
                        "message": "The weather service is temporarily unavailable.",
                        "message_key": "estimate.provider_unavailable",
                        "details": {},
                    },
                    status=503,
                )
                return
            bbox_values = [
                float(value)
                for value in query.get("bbox", [""])[0].split(",")
                if value
            ]
            if bbox_values and max(abs(value) for value in bbox_values) < 2:
                fulfill_json(
                    route,
                    {
                        "code": "outside_coverage",
                        "message": "The view contains no Italian grid square.",
                        "message_key": "map.outside_coverage",
                        "details": {},
                    },
                    status=400,
                )
                return
            response = (
                _pending_squares_response(target_date)
                if pending_squares
                else _squares_response(target_date)
            )
            if unique_calculated_times:
                for index, feature in enumerate(response["features"]):
                    feature["properties"]["calculated_at"] = f"2026-10-12T{8 + index:02d}:30:00Z"
            fulfill_json(route, response)
            return
        route.continue_()

    page.route("**/api/v1/info**", api_route)
    page.route("**/api/v1/forest-layer**", api_route)
    page.route("**/api/v1/estimate-overview**", api_route)
    page.route("**/api/v1/squares**", api_route)
    page.route("**/api/v1/areas/**", api_route)

    def style_route(route: Route) -> None:
        fulfill_json(route, _background_style(contrast="contrast" in route.request.url))

    def tile_route(route: Route) -> None:
        route.fulfill(content_type="image/png", body=TRANSPARENT_TILE)

    page.route("**/styles/**", style_route)
    page.route("**/*.json?**", style_route)
    page.route("**/*.png**", tile_route)
    return requests


def _open_map(
    page: Page,
    base_url: str,
    *,
    language: str = "en",
    viewport: tuple[int, int] = (1440, 900),
    fail_first_area_request: bool = False,
    fail_area_target_date: str | None = None,
    unique_calculated_times: bool = False,
) -> list[dict[str, object]]:
    requests = _install_map_routes(
        page,
        fail_first_area_request=fail_first_area_request,
        fail_area_target_date=fail_area_target_date,
        unique_calculated_times=unique_calculated_times,
    )
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    page.set_extra_http_headers(
        {"Accept-Language": "it-IT,it;q=0.9" if language == "it" else "en-GB,en;q=0.9"}
    )
    page.goto(
        url=f"{base_url}/map/?center=44.14,10.65&zoom=12&date={TARGET_DATES[0]}",
        wait_until="domcontentloaded",
    )
    page.wait_for_function(
        """
        () => Boolean(
          window.MicometeoMap?.map &&
          document.querySelector('#map canvas.maplibregl-canvas')
        )
        """,
        timeout=15_000,
    )
    page.wait_for_function(
        """
        () => Boolean(window.MicometeoMap?.map?.isStyleLoaded?.())
        """,
        timeout=15_000,
    )
    page.wait_for_function(
        """
        () => Boolean(window.MicometeoMap?.map?.getSource?.('squares'))
        """,
        timeout=15_000,
    )
    first_date = page.locator(f".date-btn[data-date='{TARGET_DATES[0]}']")
    first_date.click()
    _wait_for_square_request(page, requests, TARGET_DATES[0])
    return requests


def _map_snapshot(page: Page) -> dict[str, object]:
    return page.evaluate(
        """
        () => {
          const exposed = window.MicometeoMap;
          const diagnostics = typeof exposed?.getDiagnostics === 'function'
            ? exposed.getDiagnostics()
            : exposed?.diagnostics || {};
          const listeners = exposed?.map?._listeners || {};
          const listenerTotal = Object.values(listeners).reduce(
            (total, value) => total + (Array.isArray(value) ? value.length : 0), 0
          );
          return {
            instanceCount: diagnostics.mapInstances ?? diagnostics.mapInstanceCount ?? diagnostics.map_instance_count ?? null,
            listenerCount: diagnostics.listenerCount ?? diagnostics.listener_count ?? null,
            actualListenerCount: listenerTotal,
            map: Boolean(exposed?.map),
            layerIds: exposed?.map?.getStyle?.()?.layers?.map((layer) => layer.id) || [],
            sources: exposed?.map?.getStyle?.()?.sources
              ? Object.keys(exposed.map.getStyle().sources)
              : [],
          };
        }
        """
    )


def _api_requests(requests: list[dict[str, object]], path: str) -> list[dict[str, object]]:
    return [request for request in requests if request["path"].endswith(path)]


def _wait_for_square_request(page: Page, requests: list[dict[str, object]], date: str) -> None:
    for _ in range(100):
        if any(
            request["query"].get("target_date") == [date]
            for request in _api_requests(requests, "/squares")
        ):
            return
        page.wait_for_timeout(100)
    pytest.fail(f"The map did not request squares for {date}")


def _flatten(value: object) -> list[object]:
    if isinstance(value, list):
        result: list[object] = []
        for item in value:
            result.extend(_flatten(item))
        return result
    return [value]


def test_map_renders_eight_calendar_dates_and_preserves_an_older_target(
    page: Page, base_url: str
) -> None:
    requests = _open_map(page, base_url)

    dates = page.locator(".date-btn")
    expect(dates).to_have_count(8)
    assert dates.evaluate_all("(items) => items.map((item) => item.dataset.date)") == list(
        TARGET_DATES
    )
    expect(page.locator("html")).to_have_attribute("lang", "en")
    expect(page.locator(".date-btn[data-date='2026-10-12']")).to_contain_text("Today")

    page.locator(".date-btn[data-date='2026-10-15']").click()
    _wait_for_square_request(page, requests, "2026-10-15")
    expect(page.locator(".date-btn[data-date='2026-10-15']")).to_have_attribute(
        "aria-pressed", "true"
    )
    root = page.locator("[data-map-app]")
    expect(root).to_have_attribute("data-target-date", "2026-10-15")

    page.wait_for_function(
        """() => window.MicometeoMap.map.querySourceFeatures('squares')
          .some(feature => feature.properties.target_date === '2026-10-15'
            && feature.properties.assessment_date === '2026-10-11')""",
        timeout=10_000,
    )
    source_snapshot = page.evaluate(
        """
        () => {
          const map = window.MicometeoMap?.map;
          const source = map?.getSource('squares');
          return {
            source: Boolean(source),
            raw: source?._data || null,
            queried: map?.querySourceFeatures('squares') || [],
            diagnostics: window.MicometeoMap?.getDiagnostics?.() || null,
          };
        }
        """
    )
    assert any(
        feature.get("properties", {}).get("assessment_date") == "2026-10-11"
        for feature in source_snapshot["queried"]
    ), source_snapshot
    expect(root).to_have_attribute("data-target-date", "2026-10-15")
    expect(root).to_have_attribute("data-assessment-date", "2026-10-12")
    assert "2026-10-11" not in page.locator(".datecol").inner_text()


def test_mouse_drag_moves_map_with_selected_area_open(page: Page, base_url: str) -> None:
    _open_map(page, base_url)
    page.wait_for_function("""() => MicometeoMap.map.queryRenderedFeatures(
        MicometeoMap.map.project([10.64, 44.13]),
        {layers: ['micometeo-square-estimates']}
    ).some(feature => feature.properties.cell_id === 'cell-zero')""")
    page.evaluate("""() => {
        const map = MicometeoMap.map;
        const point = map.project([10.64, 44.13]);
        map.fire('click', {point, lngLat: map.unproject(point)});
    }""")
    expect(page.locator("aside[data-live-details]")).to_be_visible()
    close = page.locator(".live-details-close")
    expect(close).to_be_visible()
    assert close.evaluate("element => element.getBoundingClientRect().right <= innerWidth")
    close.click()
    expect(page.locator("aside[data-live-details]")).to_have_count(0)
    page.wait_for_function("() => !MicometeoMap.map.isMoving()")
    page.evaluate("""() => {
        const map = MicometeoMap.map;
        const point = map.project([10.64, 44.13]);
        map.fire('click', {point, lngLat: map.unproject(point)});
    }""")
    expect(page.locator("aside[data-live-details]")).to_be_visible()
    before = page.evaluate("MicometeoMap.map.getCenter().toArray()")
    layout_before = page.locator("#map").bounding_box()
    page.mouse.move(x=350, y=350)
    page.mouse.down()
    page.mouse.move(x=370, y=350, steps=4)
    page.wait_for_timeout(250)
    middle = page.evaluate("MicometeoMap.map.getCenter().lng")
    page.mouse.move(x=470, y=350, steps=12)
    page.wait_for_timeout(100)
    after = page.evaluate("MicometeoMap.map.getCenter().lng")
    page.mouse.up()
    assert abs(after - middle) > 0.005
    page.wait_for_function(
        "before => Math.abs(MicometeoMap.map.getCenter().lng - before[0]) > 0.001",
        arg=before,
    )
    page.wait_for_timeout(700)
    expect(page.locator("aside[data-live-details]")).to_be_visible()
    assert page.locator("#map").bounding_box() == layout_before
    page.evaluate("MicometeoMap.map.jumpTo({center: [11.5, 43.5]})")
    page.wait_for_timeout(700)
    expect(page.locator("aside[data-live-details]")).to_be_visible()
    assert page.locator("#map").bounding_box() == layout_before


@pytest.mark.parametrize("language", ["en", "it"])
def test_map_shows_actual_mixed_assessment_dates_and_calculation_time(
    page: Page, base_url: str, language: str
) -> None:
    requests = _open_map(page, base_url, language=language)
    page.locator(".date-btn[data-date='2026-10-15']").click()
    _wait_for_square_request(page, requests, "2026-10-15")
    expect(page.locator(".date-assess")).to_contain_text("11")
    expect(page.locator(".date-assess")).to_contain_text("12")
    expect(page.locator(".date-assess strong")).to_contain_text("2026")
    expect(page.locator("[data-date-update]")).to_be_hidden()


@pytest.mark.parametrize("language", ["en", "it"])
@pytest.mark.parametrize("viewport", [(390, 844), (1440, 900)])
def test_selected_square_loads_exact_date_percentages_and_older_warning(
    page: Page, base_url: str, language: str, viewport: tuple[int, int]
) -> None:
    requests = _open_map(page, base_url, language=language, viewport=viewport)
    page.locator(".date-btn[data-date='2026-10-15']").click()
    _wait_for_square_request(page, requests, "2026-10-15")
    page.wait_for_function(
        """
        () => window.MicometeoMap.map.queryRenderedFeatures(
          window.MicometeoMap.map.project([10.64, 44.13]),
          {layers: ['micometeo-square-estimates']}
        ).some((feature) => feature.properties?.cell_id === 'cell-zero')
        """,
        timeout=10_000,
    )
    page.evaluate(
        """
        () => {
          const map = window.MicometeoMap.map;
          const point = map.project([10.64, 44.13]);
          map.fire('click', {point, lngLat: map.unproject(point)});
        }
        """
    )
    page.wait_for_function(
        "() => document.querySelectorAll('.date-btn[data-estimate-state]').length === 8",
        timeout=10_000,
    )
    assert page.locator(".date-btn[data-date='2026-10-15'] .d-pct").inner_text() == "0%"
    assert page.locator(".date-btn[data-date='2026-10-18'] .d-pct").inner_text() == "0%"
    assert page.locator(".date-btn[data-date='2026-10-12'] .d-pct").inner_text() == "0%"
    assert page.locator(".date-btn[data-date='2026-10-19'] .d-pct").inner_text() in {"Unavailable", "Non disponibile"}
    expect(page.locator(".notice-experimental")).to_contain_text(
        "Experimental estimate" if language == "en" else "Stima sperimentale"
    )
    expect(page.locator(".legend-note").first).to_contain_text(
        "experimental estimates" if language == "en" else "stime sperimentali"
    )
    area_requests = [request for request in requests if "/areas/" in request["path"]]
    assert area_requests
    assert {request["query"]["update_id"][0] for request in area_requests} == {"update-current"}
    expect(page.locator("[data-date-warning]")).to_be_visible()
    expect(page.locator("[data-date-warning]")).to_contain_text("10:30")
    warning_box = page.locator("[data-date-warning]").bounding_box()
    datecol_box = page.locator(".datecol").bounding_box()
    assert warning_box and datecol_box
    assert warning_box["height"] > 0
    assert warning_box["y"] >= datecol_box["y"]
    assert warning_box["y"] + warning_box["height"] <= datecol_box["y"] + datecol_box["height"]


@pytest.mark.parametrize("viewport", [(390, 844), (1440, 900)])
def test_date_selector_collapses_and_preserves_state_on_reload(
    page: Page, base_url: str, viewport: tuple[int, int],
) -> None:
    _open_map(page, base_url, viewport=viewport)
    toggle = page.locator("[data-fold='dates']")
    expect(toggle).to_have_css("transform", "matrix(-1, 0, 0, -1, 0, 0)")
    toggle.click()
    expect(page.locator("#dates-body")).to_be_hidden()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(toggle).to_have_css("transform", "none")
    page.reload(wait_until="domcontentloaded")
    expect(page.locator("#dates-body")).to_be_hidden()
    expect(toggle).to_be_in_viewport()
    toggle.click()
    expect(page.locator("#dates-body")).to_be_visible()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(toggle).to_have_css("transform", "matrix(-1, 0, 0, -1, 0, 0)")


@pytest.mark.parametrize("panel", ["legend", "layers"])
def test_map_panel_arrows_point_toward_their_next_position(
    page: Page, base_url: str, panel: str,
) -> None:
    _open_map(page, base_url, viewport=(1440, 900))
    toggle = page.locator(f"[data-fold='{panel}']")
    open_transform = "matrix(-1, 0, 0, -1, 0, 0)" if panel == "legend" else "none"
    closed_transform = "none" if panel == "legend" else "matrix(-1, 0, 0, -1, 0, 0)"
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(toggle).to_have_css("transform", open_transform)
    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(toggle).to_have_css("transform", closed_transform)
    page.reload(wait_until="domcontentloaded")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(toggle).to_have_css("transform", closed_transform)
    toggle.click()
    expect(toggle).to_have_css("transform", open_transform)


def test_many_calculated_times_keep_date_strip_within_short_desktop_viewport(
    page: Page, base_url: str
) -> None:
    _open_map(
        page,
        base_url,
        viewport=(1440, 792),
        unique_calculated_times=True,
    )
    date_buttons = page.locator(".date-btn")
    expect(date_buttons).to_have_count(8)
    update = page.locator("[data-date-update]")
    expect(update).to_be_hidden()
    expect(page.locator("[data-date-warning]")).to_be_hidden()
    viewport_height = page.evaluate("() => window.innerHeight")
    boxes = [date_buttons.nth(index).bounding_box() for index in range(8)]
    assert all(box and box["y"] + box["height"] <= viewport_height for box in boxes)


def test_selected_square_area_failure_can_retry_without_cached_unavailable_result(
    page: Page, base_url: str
) -> None:
    requests = _open_map(
        page,
        base_url,
        fail_first_area_request=True,
        fail_area_target_date=TARGET_DATES[1],
    )
    page.wait_for_function(
        """
        () => window.MicometeoMap.map.queryRenderedFeatures(
          window.MicometeoMap.map.project([10.64, 44.13]),
          {layers: ['micometeo-square-estimates']}
        ).some((feature) => feature.properties?.cell_id === 'cell-zero')
        """,
        timeout=10_000,
    )
    page.evaluate(
        """
        () => {
          const map = window.MicometeoMap.map;
          const point = map.project([10.64, 44.13]);
          map.fire('click', {point, lngLat: map.unproject(point)});
        }
        """
    )
    expect(page.locator(f".date-btn[data-date='{TARGET_DATES[1]}'] .d-pct")).to_have_text("")
    expect(page.locator("[data-live-state='error']")).to_contain_text("Try again")
    page.locator("[data-live-state='error'] button").click()
    page.wait_for_function(
        "() => document.querySelector(\".date-btn[data-date='2026-10-12'] .d-pct\")?.textContent === \"0%\"",
        timeout=10_000,
    )
    expect(page.locator(f".date-btn[data-date='{TARGET_DATES[1]}'] .d-pct")).to_have_text("0%")
    area_requests = [request for request in requests if "/areas/" in request["path"]]
    assert len(area_requests) >= 8


def test_initial_and_switched_style_failures_keep_the_working_map(
    page: Page, base_url: str
) -> None:
    _install_map_routes(page)
    initial_failures = {"count": 1}

    def fail_initial_style(route: Route) -> None:
        if initial_failures["count"]:
            initial_failures["count"] -= 1
            route.fulfill(status=503, content_type="application/json", body="{}")
            return
        route.fulfill(
            content_type="application/json",
            body=json.dumps(_background_style(contrast="contrast" in route.request.url)),
        )

    page.route("**/styles/**", fail_initial_style)
    page.goto(url=f"{base_url}/map/?center=44.14,10.65&zoom=12", wait_until="domcontentloaded")
    expect(page.locator("[data-live-state='error']")).to_contain_text("background")
    page.locator("[data-live-state='error'] button").click()
    page.wait_for_function("() => Boolean(window.MicometeoMap?.map)", timeout=15_000)
    assert page.evaluate("() => window.MicometeoMap.getDiagnostics().mapInstances") == 1

    requests = _open_map(page, base_url)
    page.wait_for_function(
        """
        () => window.MicometeoMap.map.queryRenderedFeatures(
          window.MicometeoMap.map.project([10.64, 44.13]),
          {layers: ['micometeo-square-estimates']}
        ).some((feature) => feature.properties?.cell_id === 'cell-zero')
        """,
        timeout=10_000,
    )
    page.evaluate(
        """
        () => {
          const map = window.MicometeoMap.map;
          const point = map.project([10.64, 44.13]);
          map.fire('click', {point, lngLat: map.unproject(point)});
        }
        """
    )
    expect(page.locator("[data-map-app]")).to_have_attribute("data-selected-square", "cell-zero")
    switch_failures = {"count": 1}

    def fail_switched_style(route: Route) -> None:
        if "positron" in route.request.url and switch_failures["count"]:
            switch_failures["count"] -= 1
            route.fulfill(status=503, content_type="application/json", body="{}")
            return
        route.fulfill(
            content_type="application/json",
            body=json.dumps(_background_style(contrast="contrast" in route.request.url)),
        )

    page.route("**/styles/**", fail_switched_style)
    page.locator("input[name='background'][value='contrast']").click()
    expect(page.locator("[data-live-state='error']")).to_contain_text("background")
    expect(page.locator("input[name='background'][value='light']")).to_be_checked()
    expect(page.locator("[data-map-app]")).to_have_attribute("data-selected-square", "cell-zero")
    assert page.locator("#map canvas.maplibregl-canvas").count() == 1
    assert page.evaluate("() => window.MicometeoMap.getDiagnostics().mapInstances") == 1

    page.locator("[data-live-state='error'] button").click()
    page.wait_for_function(
        "() => window.MicometeoMap.map.getStyle()?.metadata?.micometeoStyle === 'contrast'",
        timeout=10_000,
    )
    expect(page.locator("input[name='background'][value='contrast']")).to_be_checked()
    expect(page.locator("[data-live-state='error']")).to_have_count(0)

    page.evaluate(
        """
        () => {
          const originalFetch = window.fetch.bind(window);
          const pending = [];
          window.__mapTestOriginalFetch = originalFetch;
          window.fetch = (input, init) => {
            const url = typeof input === 'string' ? input : input.url;
            if (!url.includes('positron')) return originalFetch(input, init);
            return new Promise((resolve, reject) => pending.push({resolve, reject}));
          };
          window.__mapTestPendingStyle = pending;
        }
        """
    )
    page.locator("input[name='background'][value='light']").check()
    page.wait_for_function(
        "() => window.MicometeoMap.map.getStyle()?.metadata?.micometeoStyle === 'light'",
        timeout=10_000,
    )
    page.locator("input[name='background'][value='contrast']").check()
    page.wait_for_function(
        "() => (window.__mapTestPendingStyle || []).length === 1", timeout=10_000
    )
    page.locator("input[name='background'][value='light']").check()
    page.evaluate(
        """
        () => window.__mapTestPendingStyle[0].resolve(new Response(
          JSON.stringify({
            version: 8,
            metadata: {micometeoStyle: 'contrast'},
            sources: {},
            layers: [],
          }),
          {status: 200, headers: {'Content-Type': 'application/json'}}
        ))
        """
    )
    page.wait_for_timeout(300)
    expect(page.locator("input[name='background'][value='light']")).to_be_checked()
    assert page.evaluate(
        "() => window.MicometeoMap.map.getStyle()?.metadata?.micometeoStyle"
    ) == "light"
    expect(page.locator("[data-live-state='error']")).to_have_count(0)
    page.evaluate("() => { window.fetch = window.__mapTestOriginalFetch; }")


def test_style_success_does_not_clear_a_newer_squares_error_or_retry_style(
    page: Page, base_url: str
) -> None:
    requests = _open_map(page, base_url)
    style_requests: list[Route] = []
    style_failures = {"count": 1}
    squares_failures = {"count": 1}

    def overlapping_style_route(route: Route) -> None:
        if "positron" in route.request.url and style_failures["count"]:
            style_failures["count"] -= 1
            route.fulfill(status=503, content_type="application/json", body="{}")
            return
        if "positron" in route.request.url:
            style_requests.append(route)
            return
        route.fulfill(
            content_type="application/json",
            body=json.dumps(_background_style(contrast="contrast" in route.request.url)),
        )

    def overlapping_squares_route(route: Route) -> None:
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        target_date = query.get("target_date", [TARGET_DATES[0]])[0]
        requests.append({"path": parsed.path, "query": query, "url": route.request.url})
        if target_date == "2026-10-16" and squares_failures["count"]:
            squares_failures["count"] -= 1
            route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps(
                    {
                        "code": "provider_unavailable",
                        "message": "The weather service is temporarily unavailable.",
                        "message_key": "estimate.provider_unavailable",
                        "details": {},
                    }
                ),
            )
            return
        route.fulfill(
            content_type="application/json",
            body=json.dumps(_squares_response(target_date)),
        )

    page.route("**/styles/**", overlapping_style_route)
    page.route("**/api/v1/squares**", overlapping_squares_route)
    page.locator("input[name='background'][value='contrast']").click()
    expect(page.locator("[data-live-state='error']")).to_contain_text("background")
    page.locator("[data-live-state='error'] button").click()
    for _ in range(100):
        if style_requests:
            break
        page.wait_for_timeout(100)
    assert len(style_requests) == 1

    page.locator(".date-btn[data-date='2026-10-16']").click()
    _wait_for_square_request(page, requests, "2026-10-16")
    expect(page.locator("[data-live-state='error']")).to_contain_text("weather service")

    style_requests[0].fulfill(
        content_type="application/json",
        body=json.dumps(_background_style(contrast=True)),
    )
    page.wait_for_function(
        "() => window.MicometeoMap.map.getStyle()?.metadata?.micometeoStyle === 'contrast'",
        timeout=10_000,
    )
    expect(page.locator("[data-live-state='error']")).to_contain_text("weather service")

    squares_before_retry = len(_api_requests(requests, "/squares"))
    page.locator("[data-live-state='error'] button").click()
    for _ in range(100):
        if len(_api_requests(requests, "/squares")) > squares_before_retry:
            break
        page.wait_for_timeout(100)
    assert len(_api_requests(requests, "/squares")) > squares_before_retry
    assert len(style_requests) == 1


def test_map_uses_canonical_weather_cell_and_center_selects_missing_states(
    page: Page, base_url: str
) -> None:
    console_errors: list[str] = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: console_errors.append(str(error)))
    requests = _open_map(page, base_url)
    page.wait_for_function(
        """
        () => window.MicometeoMap.map.queryRenderedFeatures(
          window.MicometeoMap.map.project([10.64, 44.13]),
          {layers: ['micometeo-square-estimates']}
        ).some((feature) => feature.properties?.cell_id === 'cell-zero')
        """,
        timeout=10_000,
    )
    page.evaluate(
        """
        () => {
          const map = window.MicometeoMap.map;
          const point = map.project([10.64, 44.13]);
          map.fire('click', {point, lngLat: map.unproject(point)});
        }
        """
    )
    page.wait_for_function(
        "() => window.MicometeoMap.map.querySourceFeatures('weather-area').length > 0",
        timeout=10_000,
    )
    area = page.evaluate(
        """
        () => window.MicometeoMap.map.getSource('weather-area')._data.geojson.features[0]
        """
    )
    expected_area = [
        [10.59, 44.08],
        [10.69, 44.08],
        [10.69, 44.18],
        [10.59, 44.18],
        [10.59, 44.08],
    ]
    assert all(
        point == pytest.approx(expected)
        for point, expected in zip(area["geometry"]["coordinates"][0], expected_area)
    )

    page.evaluate(
        "() => window.MicometeoMap.map.jumpTo({center: [10.655, 44.13], zoom: 12})"
    )
    _wait_for_square_request(page, requests, "2026-10-12")
    page.wait_for_function("""() => {
      const map = window.MicometeoMap.map;
      return map.queryRenderedFeatures(map.project(map.getCenter()), {layers: ['micometeo-noforest-line', 'micometeo-square-noforest']})
        .some(feature => feature.properties.cell_id === 'cell-noforest');
    }""", timeout=10_000)
    page.locator("#centre-btn").click()
    expect(page.locator("[data-map-app]")).to_have_attribute(
        "data-selected-square", "cell-noforest"
    )
    expect(page.locator("aside[data-live-details]")).to_be_visible()

    page.evaluate(
        "() => window.MicometeoMap.map.jumpTo({center: [10.650, 44.13], zoom: 12})"
    )
    _wait_for_square_request(page, requests, "2026-10-12")
    page.wait_for_function("""() => {
      const map = window.MicometeoMap.map;
      return map.queryRenderedFeatures(map.project(map.getCenter()), {layers: ['micometeo-square-missing']})
        .some(feature => feature.properties.cell_id === 'cell-missing');
    }""", timeout=10_000)
    page.locator("#centre-btn").click()
    expect(page.locator("[data-map-app]")).to_have_attribute(
        "data-selected-square", "cell-missing"
    )
    assert not console_errors


def test_map_reports_a_missing_local_map_library(
    page: Page, base_url: str
) -> None:
    _install_map_routes(page)
    page.route("**/static/maplibre-gl.mjs", lambda route: route.abort())
    page.goto(url=f"{base_url}/map/?center=44.14,10.65&zoom=12", wait_until="domcontentloaded")
    expect(page.locator("[data-live-state='error']")).to_contain_text(
        "interactive map library"
    )


def test_map_states_and_zoomed_out_scores_use_the_same_color_layer(
    page: Page, base_url: str
) -> None:
    requests = _open_map(page, base_url)
    page.wait_for_function(
        """
        () => {
          const map = window.MicometeoMap?.map;
          if (!map) return false;
          const layers = map.getStyle().layers || [];
          return layers.some((layer) => String(layer.id).includes('forest'));
        }
        """,
        timeout=10_000,
    )
    square_requests_before_zoom = len(_api_requests(requests, "/squares"))
    map_snapshot = _map_snapshot(page)
    assert map_snapshot["map"] is True
    assert "forest" in " ".join(map_snapshot["layerIds"]).lower()

    page.evaluate(
        """
        () => window.MicometeoMap.map.jumpTo({center: [10.65, 44.14], zoom: 5})
        """
    )
    for _ in range(100):
        if _api_requests(requests, "/estimate-overview"):
            break
        page.wait_for_timeout(100)
    else:
        pytest.fail("The map did not request overview scores at broad zoom")
    page.wait_for_function(
        """
        () => {
          const map = window.MicometeoMap.map;
          return map.queryRenderedFeatures({layers: ['micometeo-square-estimates']})
            .some(feature => feature.properties.overview && feature.properties.percentage === 80);
        }
        """,
        timeout=10_000,
    )
    assert len(_api_requests(requests, "/forest-layer")) == 0
    assert page.evaluate(
        """
        () => window.MicometeoMap.map.getLayoutProperty('micometeo-square-estimates', 'visibility') === 'visible'
        """
    )
    page.wait_for_timeout(600)
    assert len(_api_requests(requests, "/squares")) == square_requests_before_zoom

    page.evaluate(
        """
        () => window.MicometeoMap.map.jumpTo({center: [0, 0], zoom: 12})
        """
    )
    expect(page.locator("#mapmsgs")).to_contain_text("outside")

    page.evaluate(
        """
        () => {
          const map = window.MicometeoMap.map;
          map.jumpTo({center: [10.65, 44.14], zoom: 12});
        }
        """
    )
    page.wait_for_function("""() => window.MicometeoMap.map.queryRenderedFeatures({layers: ['micometeo-square-estimates']}).some(f => f.properties.cell_id === 'cell-zero')""", timeout=10_000)
    features = page.evaluate(
        """
        () => {
          const map = window.MicometeoMap.map;
          const layers = map.getStyle().layers || [];
          const ids = layers
            .filter((layer) => /square|noforest-line|missing-line/.test(String(layer.id)))
            .map((layer) => layer.id);
          return ids.flatMap((id) => map.queryRenderedFeatures({layers: [id]}))
            .map((feature) => feature.properties);
        }
        """
    )
    states = {feature["state"] for feature in features if feature.get("state")}
    assert {"available", "unavailable", "noforest", "noresultyet", "expired"}.issubset(
        states
    )
    percentages = {
        feature["percentage"]
        for feature in features
        if feature.get("state") == "available"
    }
    assert {0, 100}.issubset(percentages)


def test_background_overlay_opacity_and_credits_preserve_map_state(
    page: Page, base_url: str
) -> None:
    requests = _open_map(page, base_url, language="it")
    root = page.locator("[data-map-app]")
    page.locator(".date-btn[data-date='2026-10-17']").click()
    _wait_for_square_request(page, requests, "2026-10-17")
    date_before = root.get_attribute("data-target-date")
    page.wait_for_function(
        """
        () => window.MicometeoMap.map.queryRenderedFeatures(
          window.MicometeoMap.map.project([10.64, 44.13]),
          {layers: ['micometeo-square-estimates']}
        ).some((feature) => feature.properties?.cell_id === 'cell-zero')
        """,
        timeout=10_000,
    )
    page.evaluate(
        """
        () => {
          const map = window.MicometeoMap.map;
          const point = map.project([10.64, 44.13]);
          map.fire('click', {point, lngLat: map.unproject(point)});
        }
        """
    )
    expect(root).to_have_attribute("data-selected-square", "cell-zero")
    canvas_count_before = page.locator("#map canvas.maplibregl-canvas").count()

    page.locator("input[name='background'][value='contrast']").check()
    page.locator("[data-overlay]").click()
    page.locator("[data-opacity]").fill("35")
    page.locator("[data-opacity]").dispatch_event("input")
    page.wait_for_function(
        """
        () => {
          const map = window.MicometeoMap?.map;
          return Boolean(
            map?.getStyle?.()?.metadata?.micometeoStyle === 'contrast' &&
            map?.getSource('squares') &&
            map?.getLayer('micometeo-square-estimates') &&
            map?.getLayer('micometeo-forest')
          );
        }
        """,
        timeout=10_000,
    )

    expect(page.locator("input[name='background'][value='contrast']")).to_be_checked()
    expect(page.locator("[data-overlay]")).to_have_attribute("aria-checked", "false")
    expect(page.locator("[data-opacity]")).to_have_value("35")
    expect(root).to_have_attribute("data-target-date", date_before or "")
    expect(root).to_have_attribute("data-selected-square", "cell-zero")
    expect(page.locator(".attribution")).to_contain_text("OpenStreetMap")
    expect(page.locator(".attribution")).to_contain_text("Open-Meteo")
    assert page.locator("#map canvas.maplibregl-canvas").count() == canvas_count_before == 1
    assert len(_api_requests(requests, "/squares")) >= 2


def test_delayed_date_responses_cannot_replace_the_latest_overlay(
    page: Page, base_url: str
) -> None:
    requests = _open_map(page, base_url)
    pending = page.evaluate_handle(
        """
        () => {
          const pendingRequests = [];
          const originalFetch = window.fetch.bind(window);
          window.fetch = (input, init) => {
            const url = typeof input === 'string' ? input : input.url;
            if (!url.includes('/api/v1/squares')) return originalFetch(input, init);
            return new Promise((resolve) => pendingRequests.push({url, resolve}));
          };
          window.__mapTestPendingSquares = pendingRequests;
          return pendingRequests;
        }
        """
    )
    pending.dispose()
    page.locator(".date-btn[data-date='2026-10-13']").click()
    page.wait_for_function(
        "() => (window.__mapTestPendingSquares || []).length >= 1", timeout=10_000
    )
    page.evaluate(
        "() => window.MicometeoMap.map.jumpTo({center: [10.70, 44.20], zoom: 12})"
    )
    page.wait_for_function(
        "() => (window.__mapTestPendingSquares || []).length >= 2", timeout=10_000
    )
    page.locator(".date-btn[data-date='2026-10-18']").click()
    page.wait_for_function(
        "() => (window.__mapTestPendingSquares || []).length >= 3", timeout=10_000
    )
    page.evaluate(
        """
        () => {
          const pending = window.__mapTestPendingSquares;
          const response = (targetDate, percentage) => new Response(
            JSON.stringify({
              type: 'FeatureCollection', target_date: targetDate, square_count: 1,
              features: [{
                type: 'Feature', id: `latest-${targetDate}`,
                geometry: {
                  type: 'Polygon',
                  coordinates: [[[10.64, 44.13], [10.645, 44.13], [10.645, 44.135], [10.64, 44.135], [10.64, 44.13]]]
                },
                properties: {
                  state: 'available', percentage, target_date: targetDate,
                  assessment_date: '2026-10-12', update_id: `update-${targetDate}`
                }
              }]
            }), {status: 200, headers: {'Content-Type': 'application/json'}}
          );
          const latest = pending.pop();
          latest.resolve(response('2026-10-18', 100));
          window.setTimeout(() => pending.forEach(
            (entry) => entry.resolve(response('2026-10-13', 0))
          ), 50);
        }
        """
    )
    page.wait_for_function("""() => window.MicometeoMap.map.querySourceFeatures('squares')
      .some(feature => feature.properties.target_date === '2026-10-18' && feature.properties.percentage === 100)
    """, timeout=10_000)
    expect(page.locator("[data-map-app]")).to_have_attribute("data-target-date", "2026-10-18")
    expect(page.locator(".date-btn[aria-pressed='true']")).to_have_attribute(
        "data-date", "2026-10-18"
    )
    latest_target = page.evaluate(
        "() => window.MicometeoMap?.getDiagnostics?.().targetDate"
    )
    assert latest_target == "2026-10-18"
    rendered = page.evaluate(
        """
        () => window.MicometeoMap.map.querySourceFeatures('squares')
          .map((feature) => feature.properties)
        """
    )
    assert any(
        feature.get("target_date") == "2026-10-18"
        and feature.get("percentage") == 100
        for feature in rendered
    )
    assert _api_requests(requests, "/squares")


def test_date_loading_clears_selected_details_until_the_new_overlay_arrives(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    root = page.locator("[data-map-app]")
    page.wait_for_function(
        """
        () => window.MicometeoMap.map.queryRenderedFeatures(
          window.MicometeoMap.map.project([10.64, 44.13]),
          {layers: ['micometeo-square-estimates']}
        ).some((feature) => feature.properties?.cell_id === 'cell-zero')
        """,
        timeout=10_000,
    )
    page.evaluate(
        """
        () => {
          const map = window.MicometeoMap.map;
          const point = map.project([10.64, 44.13]);
          map.fire('click', {point, lngLat: map.unproject(point)});
        }
        """
    )
    expect(root).to_have_attribute("data-selected-square", "cell-zero")
    expect(page.locator("aside[data-live-details]")).to_be_visible()

    page.evaluate(
        """
        () => {
          const originalFetch = window.fetch.bind(window);
          const pending = [];
          window.fetch = (input, init) => {
            const url = typeof input === 'string' ? input : input.url;
            if (!url.includes('/api/v1/squares')) return originalFetch(input, init);
            return new Promise((resolve) => pending.push({resolve}));
          };
          window.__mapTestPendingSquares = pending;
        }
        """
    )
    page.locator(".date-btn[data-date='2026-10-18']").click()
    page.wait_for_function(
        "() => (window.__mapTestPendingSquares || []).length >= 1", timeout=10_000
    )
    expect(page.locator("[data-live-state='wait']")).to_be_visible()
    assert root.get_attribute("data-selected-square") != "cell-zero"
    expect(page.locator("aside[data-live-details]")).to_have_count(0)


def test_delayed_overview_failure_cannot_replace_the_latest_map_state(
    page: Page, base_url: str
) -> None:
    requests = _open_map(page, base_url)
    page.evaluate(
        """
        () => {
          const originalFetch = window.fetch.bind(window);
          const pending = [];
          window.fetch = (input, init) => {
            const url = typeof input === 'string' ? input : input.url;
            if (!url.includes('/api/v1/estimate-overview')) return originalFetch(input, init);
            return new Promise((resolve, reject) => pending.push({resolve, reject}));
          };
          window.__mapTestPendingForest = pending;
        }
        """
    )
    page.evaluate(
        "() => window.MicometeoMap.map.jumpTo({center: [10.65, 44.14], zoom: 5})"
    )
    page.wait_for_function(
        "() => (window.__mapTestPendingForest || []).length >= 1", timeout=10_000
    )
    page.evaluate(
        "() => window.MicometeoMap.map.jumpTo({center: [10.65, 44.14], zoom: 12})"
    )
    page.locator(".date-btn[data-date='2026-10-17']").click()
    _wait_for_square_request(page, requests, "2026-10-17")
    page.wait_for_timeout(350)
    page.evaluate(
        "() => window.__mapTestPendingForest[0]?.reject(new Error('stale forest'))"
    )
    page.wait_for_timeout(350)
    expect(page.locator("[data-map-app]")).to_have_attribute(
        "data-target-date", "2026-10-17"
    )
    expect(page.locator("[data-live-state='error']")).to_have_count(0)


def test_failed_squares_request_offers_retry_without_losing_the_selected_date(
    page: Page, base_url: str
) -> None:
    _open_map(page=page, base_url=base_url)
    expect(page.locator("[data-live-state='wait']")).to_contain_text("pending")
    requests = _install_map_routes(page=page, fail_first_squares_request=True)
    page.locator(".date-btn[data-date='2026-10-16']").click()
    _wait_for_square_request(page, requests, "2026-10-16")
    expect(page.locator("[data-live-state='error']")).to_be_visible()
    expect(page.locator("[data-live-state='error']")).to_contain_text("Try again")

    retry = page.locator("[data-live-state='error'] button")
    expect(retry).to_be_visible()
    retry.click()
    page.wait_for_timeout(500)
    expect(page.locator("[data-map-app]")).to_have_attribute("data-target-date", "2026-10-16")
    expect(page.locator("[data-live-state='error']")).to_have_count(0)
    expect(page.locator("[data-live-state='wait']")).to_contain_text("pending")
    assert len(_api_requests(requests, "/squares")) >= 2


def test_pending_results_offer_retry_after_automatic_waits_are_exhausted(
    page: Page, base_url: str
) -> None:
    requests = _install_map_routes(page, pending_squares=True)
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(
        url=f"{base_url}/map/?center=44.14,10.65&zoom=12",
        wait_until="domcontentloaded",
    )
    page.wait_for_function(
        "() => Boolean(window.MicometeoMap?.map && document.querySelector('#map canvas.maplibregl-canvas'))",
        timeout=15_000,
    )
    page.locator(".date-btn[data-date='2026-10-16']").click()
    _wait_for_square_request(page, requests, "2026-10-16")
    page.wait_for_timeout(6_200)
    expect(page.locator("[data-live-state='error']")).to_be_visible()
    expect(page.locator("[data-live-state='error'] button")).to_be_visible()


def test_repeated_controls_keep_one_map_and_do_not_report_console_errors(
    page: Page, base_url: str
) -> None:
    console_errors: list[str] = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: console_errors.append(str(error)))
    requests = _open_map(page, base_url)
    initial_snapshot = _map_snapshot(page)

    for background in ("contrast", "light", "contrast", "light"):
        page.locator(f"input[name='background'][value='{background}']").check()
        page.locator("[data-opacity]").fill("45")
        page.locator("[data-opacity]").dispatch_event("input")
        page.locator("[data-overlay]").click()
        page.locator("[data-overlay]").click()
        page.locator(".date-btn[data-date='2026-10-16']").click()
        page.locator(".date-btn[data-date='2026-10-12']").click()
        page.evaluate(
            """
            () => window.MicometeoMap.map.jumpTo({center: [10.65, 44.14], zoom: 12})
            """
        )

    page.wait_for_timeout(800)
    final_snapshot = _map_snapshot(page)
    assert page.locator("#map canvas.maplibregl-canvas").count() == 1
    assert initial_snapshot["map"] is True
    assert final_snapshot["map"] is True
    if initial_snapshot["instanceCount"] is not None:
        assert final_snapshot["instanceCount"] == initial_snapshot["instanceCount"] == 1
    if initial_snapshot["listenerCount"] is not None:
        assert final_snapshot["listenerCount"] == initial_snapshot["listenerCount"]
    assert final_snapshot["actualListenerCount"] == initial_snapshot["actualListenerCount"]
    assert not console_errors
    assert len(_api_requests(requests, "/squares")) <= 20


def test_estimate_scale_has_exact_endpoints_and_separate_status_looks(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    swatches = page.locator(".lg-compact .lg-scale .lg-chip i")
    expect(swatches).to_have_count(5)
    colors = swatches.evaluate_all(
        "(items) => items.map((item) => getComputedStyle(item).backgroundColor)"
    )
    assert colors[0] in {"rgb(255, 249, 240)", "#fff9f0"}
    assert colors[-1] in {"rgb(67, 36, 117)", "#432475"}

    layer_paint = page.evaluate(
        """
        () => {
          const map = window.MicometeoMap.map;
          const layers = map.getStyle().layers || [];
          return layers
            .filter((layer) => /square|noforest-line|missing-line/.test(String(layer.id)))
            .map((layer) => ({
              id: layer.id,
              type: layer.type,
              filter: layer.filter || null,
              color: layer.paint?.['fill-color'] || null,
              pattern: layer.paint?.['fill-pattern'] || null,
            }));
        }
        """
    )
    estimate_colors = {
        str(value).lower()
        for item in layer_paint
        for value in _flatten(item["color"])
        if isinstance(value, str)
    }
    assert "#fff9f0" in estimate_colors
    assert {"#e5ac43", "#24958b", "#7851b5", "#432475"}.issubset(estimate_colors)
    status_layers = " ".join(item["id"] for item in layer_paint).lower()
    assert "missing" in status_layers
    assert "noforest" in status_layers or "no-forest" in status_layers
    missing_layer = next(item for item in layer_paint if "missing" in item["id"])
    noforest_candidates = [item for item in layer_paint if "noforest" in item["id"]]
    assert noforest_candidates, layer_paint
    noforest_layer = noforest_candidates[-1]
    assert missing_layer["pattern"] == "micometeo-missing"
    assert noforest_layer["type"] == "line"
    assert noforest_layer["filter"] == ["==", ["get", "state"], "noforest"]

    forest_paint = page.evaluate(
        """
        () => window.MicometeoMap.map.getStyle().layers
          .find((layer) => layer.id === 'micometeo-forest')?.paint?.['fill-color']
        """
    )
    forest_colors = {
        str(value).lower()
        for value in _flatten(forest_paint)
        if isinstance(value, str)
    }
    assert "rgba(60,110,89,0)" in forest_colors
    assert "rgba(60,110,89,0.58)" in forest_colors


@pytest.mark.parametrize("language", ["en", "it"])
@pytest.mark.parametrize("viewport", [(390, 844), (1440, 900)])
def test_live_map_fits_phone_and_desktop_in_both_languages(
    page: Page,
    base_url: str,
    language: str,
    viewport: tuple[int, int],
) -> None:
    _open_map(page, base_url, language=language, viewport=viewport)
    expect(page.locator("html")).to_have_attribute("lang", language)
    expect(page.locator(".date-btn")).to_have_count(8)
    expect(page.locator("#map canvas.maplibregl-canvas")).to_be_visible()
    dimensions = page.locator("html").evaluate(
        """
        (element) => ({
          pageWidth: element.scrollWidth,
          viewportWidth: document.documentElement.clientWidth,
        })
        """
    )
    assert dimensions["pageWidth"] <= dimensions["viewportWidth"]
