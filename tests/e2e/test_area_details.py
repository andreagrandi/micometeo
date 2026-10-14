from __future__ import annotations

import json
import re
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import Page, Route, expect

from tests.e2e.test_map_controls import (
    TARGET_DATES,
    _open_map,
    _polygon,
    _squares_response,
    _wait_for_map_settled,
)


def _full_area_response(
    *,
    cell_id: str,
    target_date: str,
    update_id: str = "update-current",
    percentage: int | None = 0,
    assessment_date: str = "2026-10-12",
    optional_gap: bool = False,
    recent_rain: float = 12.5,
    unavailable_reason: str | None = None,
    host_facts: bool = False,
    missing_host_factor: bool = False,
    weather_gaps: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    end = date.fromisoformat(assessment_date) - timedelta(days=1)
    recent_start = end - timedelta(days=6)
    facts: list[dict[str, object]] = [
        {
            "role_key": "recent_rain",
            "role": "recent_rain",
            "actual_value": recent_rain,
            "value": recent_rain,
            "unit": "mm",
            "period_start": recent_start.isoformat(),
            "period_end": end.isoformat(),
            "period": {"start": recent_start.isoformat(), "end": end.isoformat(), "inclusive": True},
            "source_id": "weather:fixture",
            "source_ids": ["weather:fixture"],
            "source": {"id": "weather:fixture", "ids": ["weather:fixture"]},
            "completed_day_count": 7,
            "forecast_day_count": 0,
            "method_factor": 0.7,
            "normalized_factor": 0.7,
            "translation_key": "forecast.fact.recent_rain",
        },
        {
            "role_key": "forest_share",
            "role": "forest_share",
            "actual_value": 0.68,
            "value": 0.68,
            "unit": "fraction",
            "period_start": assessment_date,
            "period_end": assessment_date,
            "period": {"start": assessment_date, "end": assessment_date, "inclusive": True},
            "source_id": "forest:fixture",
            "source_ids": ["forest:fixture"],
            "source": {"id": "forest:fixture", "ids": ["forest:fixture"]},
            "completed_day_count": 0,
            "forecast_day_count": 0,
            "method_factor": 0.64,
            "normalized_factor": 0.64,
            "translation_key": "forecast.fact.forest_share",
        },
        {
            "role_key": "corrected_mean_temperature",
            "role": "corrected_mean_temperature",
            "actual_value": 13.0,
            "value": 13.0,
            "unit": "deg_c",
            "period_start": target_date,
            "period_end": target_date,
            "period": {"start": target_date, "end": target_date, "inclusive": True},
            "source_id": "weather:fixture",
            "source_ids": ["weather:fixture"],
            "source": {"id": "weather:fixture", "ids": ["weather:fixture"]},
            "completed_day_count": 0,
            "forecast_day_count": 1,
            "method_factor": 0.8,
            "normalized_factor": 0.8,
            "translation_key": "forecast.fact.corrected_mean_temperature",
        },
    ]
    if host_facts:
        facts.append({
            "role_key": "host_beech",
            "role": "host_beech",
            "actual_value": 0.42,
            "value": 0.42,
            "unit": "relative_occurrence",
            "period_start": "2006-01-01",
            "period_end": "2006-12-31",
            "period": {"start": "2006-01-01", "end": "2006-12-31", "inclusive": True},
            "source_id": "jrc:fixture",
            "source_ids": ["jrc:fixture"],
            "source": {"id": "jrc:fixture", "ids": ["jrc:fixture"]},
            "completed_day_count": 0,
            "forecast_day_count": 0,
            "method_factor": None,
            "normalized_factor": None,
            "translation_key": "forecast.fact.host_beech",
            "quality": "modelled_1km_not_tree_cover",
            "source_metadata": {
                "credit": "JRC European Atlas of Forest Tree Species",
                "licence": "European Commission reuse notice",
                "resolution_m": 1000,
                "sampling_version": "jrc-fixture-v1",
                "source_url": "https://example.test/jrc",
            },
        })
    if missing_host_factor:
        facts.append({
            "role_key": "host_tree_factor",
            "role": "host_tree_factor",
            "actual_value": 1.0,
            "value": 1.0,
            "unit": "multiplier",
            "period_start": assessment_date,
            "period_end": assessment_date,
            "period": {"start": assessment_date, "end": assessment_date, "inclusive": True},
            "source_id": "unavailable:host_trees",
            "source_ids": ["unavailable:host_trees"],
            "source": {"id": "unavailable:host_trees", "ids": ["unavailable:host_trees"]},
            "completed_day_count": 0,
            "forecast_day_count": 0,
            "method_factor": 1.0,
            "normalized_factor": 1.0,
            "translation_key": "forecast.fact.host_tree_factor",
            "quality": "forest_only_missing_host_data",
        })
    return {
        "selection": {
            "square_id": cell_id,
            "geometry": {
                "type": "Polygon",
                "coordinates": _polygon(10.64, 44.13),
            },
            "bounds": {"west": 10.63, "south": 44.12, "east": 10.65, "north": 44.14},
            "centroid": {"latitude": 44.13, "longitude": 10.64},
            "representative_coordinates": {"latitude": 44.1312, "longitude": 10.6413},
            "target_date": target_date,
            "assessment_date": assessment_date,
            "days_ahead": (date.fromisoformat(target_date) - date.fromisoformat(assessment_date)).days,
            "update_id": update_id,
        },
        "estimate": {
            "state": "available" if percentage is not None else "unavailable",
            "whole_percentage": percentage,
            "unavailable_reason": None if percentage is not None else unavailable_reason or "missing_forest_data",
            "calculated_at": "2026-10-12T08:30:00Z",
            "method_version": "fixture-v3",
            "experimental_unvalidated": True,
            "experimental_explanation_key": "estimate.experimental_unvalidated",
            "translation_key": "estimate.available" if percentage is not None else f"estimate.{unavailable_reason or 'missing_forest_data'}",
        },
        "facts": facts,
        "weather": {
            "selected_day": {
                "state": "available",
                "date": target_date,
                "rain_mm": 2.0,
                "mean_temperature_c": 13.0,
                "min_temperature_c": 8.0,
                "completed_day_count": 0,
                "forecast_day_count": 1,
                "source_ids": ["weather:fixture"],
                "source_attempt_ids": ["attempt:fixture"],
                "missing_reason_key": None,
                "et0_mm": None if optional_gap else 1.2,
                "mean_soil_temperature_c": None,
                "mean_soil_moisture": 0.31,
                "frost": False,
            },
            "recent_rain_7_days": {
                "state": "available", "value": recent_rain, "unit": "mm",
                "period_start": recent_start.isoformat(), "period_end": end.isoformat(),
                "inclusive": True, "completed_day_count": 7, "forecast_day_count": 0,
                "source_ids": ["weather:fixture"], "source_attempt_ids": ["attempt:fixture"],
                "missing_reason_key": None,
            },
            "recent_rain_14_days": {
                "state": "available", "value": 24.5, "unit": "mm",
                "period_start": (end - timedelta(days=13)).isoformat(), "period_end": end.isoformat(),
                "inclusive": True, "completed_day_count": 14, "forecast_day_count": 0,
                "source_ids": ["weather:fixture"], "source_attempt_ids": ["attempt:fixture"],
                "missing_reason_key": None,
            },
            "recent_rain_21_days": {
                "state": "available", "value": 36.5, "unit": "mm",
                "period_start": (end - timedelta(days=20)).isoformat(), "period_end": end.isoformat(),
                "inclusive": True, "completed_day_count": 21, "forecast_day_count": 0,
                "source_ids": ["weather:fixture"], "source_attempt_ids": ["attempt:fixture"],
                "missing_reason_key": None,
            },
            "provider": "Open-Meteo",
            "model": "ecmwf_ifs04",
            "endpoint": "https://example.test/weather",
            "retrieval_time": "2026-10-11T10:00:00Z",
            "source_ids": ["weather:fixture"],
            "source_attempt_ids": ["attempt:fixture"],
            "requested_coordinates": {"latitude": 44.15, "longitude": 10.65},
            "returned_coordinates": {"latitude": 44.151, "longitude": 10.651},
            "reference_elevation_m": 500,
            "variable_gaps": weather_gaps or ([{"date": target_date, "variable": "et0", "reason_key": "optional_variable_absent"}] if optional_gap else []),
            "limitation_keys": ["weather.shared_across_several_kilometres"],
        },
        "sources": {
            "grid": {"name": "ISTAT fixture grid", "release": "2024", "source_metadata": {"survey_year": 2024}, "source_tiles": [], "gaps": [], "credit": "ISTAT", "licence": "CC BY 4.0"},
            "forest": {"name": "Copernicus forest fixture", "release": "2018", "native_resolution_m": 10, "retrieval_time": "2026-10-10T10:00:00Z", "source_metadata": {"survey_year": 2018}, "source_tiles": [], "gaps": [], "credit": "European Union", "licence": "Copernicus licence"},
            "terrain": {"name": "Copernicus DEM fixture", "release": "2021", "source_metadata": {"native_resolution_m": 30}, "source_tiles": [], "gaps": [], "credit": "Copernicus", "licence": "WorldDEM licence"},
            "weather": {"provider": "Open-Meteo", "model": "ecmwf_ifs04", "retrieval_time": "2026-10-11T10:00:00Z", "source_ids": ["weather:fixture"], "source_attempt_ids": ["attempt:fixture"], "requested_coordinates": {"latitude": 44.15, "longitude": 10.65}, "returned_coordinates": {"latitude": 44.151, "longitude": 10.651}, "reference_elevation_m": 500, "variable_gaps": [], "credit": {"text": "Weather data by Open-Meteo.com", "url": "https://open-meteo.com/", "licence": "CC BY 4.0"}},
            "limitation_keys": ["weather.shared_across_several_kilometres"],
        },
    }


def _install_detail_route(
    page: Page,
    *,
    optional_gap: bool = False,
    recent_rain_by_date: dict[str, float] | None = None,
    unavailable_dates: set[str] | None = None,
    unavailable_reason_by_date: dict[str, str] | None = None,
    host_facts: bool = False,
    missing_host_factor: bool = False,
    weather_gaps: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    requests: list[dict[str, object]] = []

    def detail_route(route: Route) -> None:
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        requests.append({"path": parsed.path, "query": query})
        square_id = parsed.path.rsplit("/", 1)[-1]
        target_date = query.get("target_date", [TARGET_DATES[0]])[0]
        update_id = query.get("update_id", [""])[0]
        if square_id == "cell-missing" and not update_id:
            route.fulfill(status=409, content_type="application/json", body=json.dumps({"code": "missing_forest_data"}))
            return
        assessment = "2026-10-11" if target_date == "2026-10-15" else "2026-10-12"
        unavailable = target_date in (unavailable_dates or set())
        unavailable_reason = (unavailable_reason_by_date or {}).get(target_date)
        route.fulfill(
            content_type="application/json",
            body=json.dumps(_full_area_response(
                cell_id=square_id,
                target_date=target_date,
                update_id=update_id or "update-current",
                assessment_date=assessment,
                optional_gap=optional_gap,
                recent_rain=(recent_rain_by_date or {}).get(target_date, 12.5),
                percentage=None if unavailable or unavailable_reason else 0,
                unavailable_reason=unavailable_reason or ("recent_rain" if unavailable else None),
                host_facts=host_facts,
                missing_host_factor=missing_host_factor,
                weather_gaps=weather_gaps,
            )),
        )

    page.route("**/api/v1/areas/**", detail_route)
    return requests


def _install_unavailable_map_route(
    page: Page, *, target_date: str, reason: str = "recent_rain"
) -> None:
    def squares_route(route: Route) -> None:
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        requested_date = query.get("target_date", [""])[0]
        response = _squares_response(requested_date)
        if requested_date == target_date:
            for feature in response["features"]:
                if feature["properties"].get("cell_id") != "cell-zero":
                    continue
                feature["properties"].update(
                    {
                        "state": "available",
                        "percentage": None,
                        "unavailable_reason": reason,
                        "reason": reason,
                        "update_id": "update-current",
                        "message_key": f"estimate.{reason}",
                    }
                )
        route.fulfill(content_type="application/json", body=json.dumps(response))

    page.route("**/api/v1/squares**", squares_route)


def _click_square(page: Page, square_id: str = "cell-zero") -> None:
    page.wait_for_function(
        """squareId => document.querySelector('[data-map-app]').dataset.mapStale !== 'true'
        && window.MicometeoMap.map.queryRenderedFeatures(
          window.MicometeoMap.map.project([
            squareId === 'cell-missing' ? 10.65 : squareId === 'cell-hundred' ? 10.645 : 10.64,
            44.13,
          ]),
          {layers: ['micometeo-square-estimates', 'micometeo-square-missing']}
        ).some((feature) => feature.properties?.cell_id === squareId)""",
        arg=square_id,
        timeout=10_000,
    )
    page.evaluate(
        """squareId => {
          const map = window.MicometeoMap.map;
          const longitude = squareId === 'cell-missing' ? 10.65
            : squareId === 'cell-hundred' ? 10.645
            : 10.64;
          const point = map.project([longitude, 44.13]);
          map.fire('click', {
            point,
            lngLat: map.unproject(point),
            originalEvent: {type: 'click', target: map.getCanvas()},
          });
        }""",
        square_id,
    )


@pytest.mark.parametrize("language", ["en", "it"])
def test_area_detail_renders_api_facts_weather_rain_sources_and_language(
    page: Page, base_url: str, language: str
) -> None:
    _open_map(page, base_url, language=language)
    requests = _install_detail_route(page)
    _click_square(page)
    expect(page.locator("aside[data-live-details]")).to_be_visible()
    page.wait_for_function("() => Boolean(document.querySelector('[data-detail-experimental]'))")
    detail = page.locator("aside[data-live-details]")
    expect(detail).to_contain_text("cell-zero")
    expect(detail).to_contain_text("0%")
    expect(detail).to_contain_text("12,5 mm" if language == "it" else "12.5 mm")
    detail.locator("[data-detail-disclosure='weather-extra'] > summary").click()
    expect(detail.locator(".detail-weather-extra")).to_contain_text(
        "0,3 m³/m³" if language == "it" else "0.3 m³/m³"
    )
    expect(detail).to_contain_text("Open-Meteo")
    expect(detail).to_contain_text("CC BY 4.0")
    expect(detail).to_contain_text("several kilometres" if language == "en" else "diversi chilometri")
    expect(detail).not_to_contain_text("confidence")
    expect(detail).not_to_contain_text("Hail")
    assert requests[0]["query"]["target_date"] == ["2026-10-12"]
    assert requests[0]["query"]["update_id"] == ["update-current"]
    page.locator("[data-rain-days='14']").click()
    expect(detail.locator(".detail-rain-value")).to_contain_text("24,5 mm" if language == "it" else "24.5 mm")
    expect(detail).to_contain_text("September" if language == "en" else "settembre")


@pytest.mark.parametrize("language", ["en", "it"])
def test_area_detail_keeps_long_facts_and_sources_folded_and_accessible(
    page: Page, base_url: str, language: str
) -> None:
    _open_map(page, base_url, language=language)
    credit = "Copernicus elevation credit. " * 12

    def detail_route(route: Route) -> None:
        parsed = urlparse(url=route.request.url)
        query = parse_qs(qs=parsed.query)
        response = _full_area_response(
            cell_id=parsed.path.rsplit("/", maxsplit=1)[-1],
            target_date=query["target_date"][0],
            host_facts=True,
        )
        host = response["facts"][-1]
        for role in ["host_chestnut", "host_oaks", "host_pines", "host_spruce_fir"]:
            response["facts"].append({**host, "role_key": role})
        response["sources"]["forest"].update({
            "name": "2018",
            "source_metadata": {"source_release": "2018", "source_resolution_m": 10},
            "service_url": "https://example.test/forest",
            "url": "https://example.test/forest",
        })
        response["sources"]["terrain"].update({
            "credit": credit,
            "licence": credit,
            "source_tiles": [{"tile_name": "N44_00_E010_00", "credit": credit}],
            "gaps": [
                {"reason_key": "No valid elevation pixels in the source window"},
                {"reason_key": "source_missing", "detail": "Missing tile N44_00_E010_00"},
            ],
        })
        route.fulfill(content_type="application/json", body=json.dumps(obj=response))

    page.route("**/api/v1/areas/**", detail_route)
    _click_square(page)
    detail = page.locator("aside[data-live-details]")
    facts = detail.locator("[data-detail-disclosure='facts']")
    sources = detail.locator("[data-detail-disclosure='sources']")
    expect(detail.locator(".detail-key-facts > li")).to_have_count(3)
    expect(facts).not_to_have_attribute("open", "")
    expect(sources).not_to_have_attribute("open", "")
    expect(detail.locator(".source-card").first).not_to_be_visible()
    expect(detail.locator(".facts-more")).not_to_be_visible()
    assert "Copernicus elevation credit" not in detail.inner_text()
    assert "2006" not in detail.inner_text()

    facts.locator(":scope > summary").focus()
    page.keyboard.press("Enter")
    expect(detail.locator(".facts-more")).to_be_visible()
    expect(detail.locator(".facts-more")).to_contain_text("2006")
    expect(detail.locator(".facts-more")).to_contain_text("42,0 %" if language == "it" else "42.0 %")
    expect(facts.locator(".fact-quality")).to_have_count(1)

    sources.locator(":scope > summary").focus()
    page.keyboard.press("Enter")
    expect(detail.locator(".source-card").first).to_be_visible()
    weather_name = "Meteo modellato Open-Meteo" if language == "it" else "Open-Meteo modelled weather"
    expect(sources.locator(".source-name", has_text=weather_name)).to_be_visible()
    expect(sources.locator(".source-name", has_text=re.compile(r"^2018$"))).to_have_count(0)
    expect(sources.locator("a[href='https://example.test/forest']")).to_have_count(1)
    assert all(not text.startswith("https://") for text in sources.locator("a").all_text_contents())
    assert sources.text_content().count(credit.strip()) == 1
    assert "Copernicus elevation credit" not in sources.inner_text()
    expect(sources.locator(".source-gap", has_text="No valid elevation pixels")).to_be_visible()
    expect(sources.locator(".source-gap", has_text="Missing tile N44_00_E010_00")).to_be_visible()

    rain_button = detail.locator("[data-rain-days='14']")
    rain_button.focus()
    page.keyboard.press("Enter")
    expect(rain_button).to_be_focused()
    expect(facts).to_have_attribute("open", "")
    expect(sources).to_have_attribute("open", "")
    expect(detail.locator(".detail-rain-value")).to_contain_text("24,5 mm" if language == "it" else "24.5 mm")

    _click_square(page, "cell-hundred")
    expect(detail.locator("#details-heading")).to_have_text("cell-hundred")
    expect(facts).not_to_have_attribute("open", "")
    expect(sources).not_to_have_attribute("open", "")


def test_area_detail_tracks_target_date_and_api_representative_after_date_change(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    requests = _install_detail_route(page)
    _click_square(page)
    page.wait_for_function("() => Boolean(document.querySelector('[data-detail-experimental]'))")
    page.locator(".date-btn[data-date='2026-10-15']").click()
    page.wait_for_function(
        "() => document.querySelector('[data-map-app]')?.dataset.targetDate === '2026-10-15'"
    )
    page.wait_for_function(
        "() => document.querySelector('aside[data-live-details]')?.textContent.includes('15 October 2026')",
        timeout=10_000,
    )
    expect(page.locator("aside[data-live-details]")).to_contain_text(
        "older result from 11 October 2026"
    )
    page.locator("[data-rain-days='14']").click()
    expect(page.locator("aside[data-live-details]")).to_contain_text("10 October 2026")
    assert any(request["query"].get("target_date") == ["2026-10-15"] for request in requests)
    root = page.locator("[data-map-app]")
    diagnostics = page.evaluate("() => window.MicometeoMap.getDiagnostics()")
    assert root.get_attribute("data-representative-latitude") == "44.1312", repr(diagnostics)
    assert root.get_attribute("data-representative-longitude") == "10.6413"


@pytest.mark.parametrize("language", ["en", "it"])
@pytest.mark.parametrize("target_date", ["2026-10-12", "2026-10-15"])
def test_area_detail_rain_periods_use_completed_days_for_each_target_and_language(
    page: Page, base_url: str, language: str, target_date: str
) -> None:
    _open_map(page, base_url, language=language)
    _install_detail_route(page)
    _click_square(page)
    detail = page.locator("aside[data-live-details]")
    page.wait_for_function("() => Boolean(document.querySelector('[data-detail-experimental]'))")
    if target_date != TARGET_DATES[0]:
        page.locator(f".date-btn[data-date='{target_date}']").click()
        page.wait_for_function(
            "target => document.querySelector('[data-map-app]')?.dataset.targetDate === target",
            arg=target_date,
        )
    if target_date == TARGET_DATES[0]:
        end_date = "11 ottobre 2026" if language == "it" else "11 October 2026"
    else:
        end_date = "10 ottobre 2026" if language == "it" else "10 October 2026"
    values = {
        7: "12,5 mm" if language == "it" else "12.5 mm",
        14: "24,5 mm" if language == "it" else "24.5 mm",
        21: "36,5 mm" if language == "it" else "36.5 mm",
    }
    for days, value in values.items():
        page.locator(f"[data-rain-days='{days}']").click()
        expect(detail.locator(".detail-rain-value")).to_contain_text(value)
        expect(detail.locator(".detail-rain-value")).to_contain_text(end_date)
        expect(detail.locator(".detail-rain-value")).not_to_contain_text(
            "12 October 2026" if language == "en" else "12 ottobre 2026"
        )


def test_area_detail_refreshes_facts_when_target_date_changes(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    _install_detail_route(page, recent_rain_by_date={"2026-10-15": 18.5})
    _click_square(page)
    detail = page.locator("aside[data-live-details]")
    page.wait_for_function("() => Boolean(document.querySelector('[data-detail-experimental]'))")
    expect(detail).to_contain_text("12.5 mm")

    page.locator(".date-btn[data-date='2026-10-15']").click()
    page.wait_for_function(
        "() => document.querySelector('[data-map-app]')?.dataset.targetDate === '2026-10-15'"
    )
    expect(detail).to_contain_text("18.5 mm", timeout=10_000)
    expect(detail).not_to_contain_text("12.5 mm")


def test_area_detail_ignores_a_late_response_from_a_previous_square(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    pending: list[Route] = []
    armed = False

    def race_route(route: Route) -> None:
        nonlocal armed
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        square_id = parsed.path.rsplit("/", 1)[-1]
        target_date = query.get("target_date", [TARGET_DATES[0]])[0]
        update_id = query.get("update_id", [""])[0] or "update-current"
        if armed and square_id == "cell-zero" and not pending:
            pending.append(route)
            return
        percentage = 100 if square_id == "cell-hundred" else 0
        route.fulfill(
            content_type="application/json",
            body=json.dumps(_full_area_response(
                cell_id=square_id,
                target_date=target_date,
                update_id=update_id,
                percentage=percentage,
            )),
        )

    page.route("**/api/v1/areas/**", race_route)
    page.wait_for_timeout(500)
    armed = True
    _click_square(page, "cell-zero")
    _click_square(page, "cell-hundred")
    detail = page.locator("aside[data-live-details]")
    expect(detail).to_contain_text("cell-hundred", timeout=10_000)
    expect(detail).to_contain_text("100%")
    assert pending, "the first area response was not held"

    pending[0].fulfill(
        content_type="application/json",
        body=json.dumps(_full_area_response(
            cell_id="cell-zero",
            target_date=TARGET_DATES[0],
            percentage=0,
            update_id="update-stale",
        )),
    )
    page.wait_for_timeout(100)
    expect(detail).to_contain_text("cell-hundred")
    expect(detail).to_contain_text("100%")


def test_area_detail_ignores_a_late_date_response_after_a_new_target_is_selected(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    pending: list[Route] = []
    armed = False

    def date_route(route: Route) -> None:
        nonlocal armed
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        square_id = parsed.path.rsplit("/", 1)[-1]
        target_date = query.get("target_date", [TARGET_DATES[0]])[0]
        update_id = query.get("update_id", [""])[0] or "update-current"
        if armed and target_date == TARGET_DATES[0] and square_id == "cell-zero" and not pending:
            pending.append(route)
            return
        route.fulfill(
            content_type="application/json",
            body=json.dumps(_full_area_response(
                cell_id=square_id,
                target_date=target_date,
                update_id=update_id,
                assessment_date="2026-10-11" if target_date == "2026-10-13" else "2026-10-12",
            )),
        )

    page.route("**/api/v1/areas/**", date_route)
    page.wait_for_timeout(500)
    armed = True
    _click_square(page)
    page.locator(".date-btn[data-date='2026-10-13']").click()
    detail = page.locator("aside[data-live-details]")
    expect(detail).to_contain_text("13 October 2026", timeout=10_000)
    assert pending, "the old target response was not held"
    pending[0].fulfill(
        content_type="application/json",
        body=json.dumps(_full_area_response(
            cell_id="cell-zero",
            target_date=TARGET_DATES[0],
            percentage=0,
        )),
    )
    page.wait_for_timeout(100)
    expect(detail).to_contain_text("13 October 2026")
    expect(detail).not_to_contain_text("12 October 2026")


def test_area_detail_close_cancels_a_pending_response(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    pending: list[Route] = []
    armed = False

    def close_route(route: Route) -> None:
        nonlocal armed
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        square_id = parsed.path.rsplit("/", 1)[-1]
        target_date = query.get("target_date", [TARGET_DATES[0]])[0]
        update_id = query.get("update_id", [""])[0] or "update-current"
        if armed and square_id == "cell-zero" and target_date == TARGET_DATES[0] and not pending:
            pending.append(route)
            return
        route.fulfill(
            content_type="application/json",
            body=json.dumps(_full_area_response(
                cell_id=square_id,
                target_date=target_date,
                update_id=update_id,
            )),
        )

    page.route("**/api/v1/areas/**", close_route)
    page.wait_for_timeout(500)
    armed = True
    _click_square(page)
    expect(page.locator("aside[data-live-details]")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("aside[data-live-details]")).to_have_count(0)
    assert pending, "the area response was not held"
    pending[0].fulfill(
        content_type="application/json",
        body=json.dumps(_full_area_response(
            cell_id="cell-zero",
            target_date=TARGET_DATES[0],
        )),
    )
    page.wait_for_timeout(100)
    expect(page.locator("aside[data-live-details]")).to_have_count(0)


def test_area_detail_keeps_facts_and_sources_for_a_full_unavailable_estimate(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    _install_unavailable_map_route(page, target_date="2026-10-13")
    _install_detail_route(page, unavailable_dates={"2026-10-13"})
    page.locator(".date-btn[data-date='2026-10-13']").click()
    _click_square(page)
    detail = page.locator("aside[data-live-details]")
    expect(detail).to_contain_text("No estimate is available", timeout=10_000)
    expect(detail).not_to_contain_text("0%")
    detail.locator("[data-detail-disclosure='facts'] > summary").click()
    rain_fact = detail.locator(".facts-more .fact-row", has_text="Rain in the recent period")
    expect(rain_fact).to_be_visible()
    expect(rain_fact).to_contain_text("12.5 mm")
    expect(rain_fact).to_contain_text("5 October 2026 - 11 October 2026")
    detail.locator("[data-detail-disclosure='sources'] > summary").click()
    weather_source = detail.locator(".source-card", has_text="Open-Meteo")
    expect(weather_source).to_be_visible()
    expect(weather_source).to_contain_text("CC BY 4.0")


def test_area_detail_retries_a_failed_request_without_losing_the_selection(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    failed = True
    armed = False

    def failed_route(route: Route) -> None:
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        square_id = parsed.path.rsplit("/", 1)[-1]
        target_date = query.get("target_date", [TARGET_DATES[0]])[0]
        update_id = query.get("update_id", [""])[0] or "update-current"
        if armed and failed and square_id == "cell-zero" and target_date == TARGET_DATES[0]:
            route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps({"code": "provider_unavailable"}),
            )
            return
        route.fulfill(
            content_type="application/json",
            body=json.dumps(_full_area_response(
                cell_id=square_id,
                target_date=target_date,
                update_id=update_id,
            )),
        )

    page.route("**/api/v1/areas/**", failed_route)
    page.wait_for_timeout(500)
    armed = True
    _click_square(page)
    detail = page.locator("aside[data-live-details]")
    expect(detail.locator(".callout-error")).to_contain_text("request failed", timeout=10_000)
    failed = False
    detail.locator(".callout-error button").click()
    expect(detail).to_contain_text("12.5 mm", timeout=10_000)
    expect(detail).to_contain_text("cell-zero")


@pytest.mark.parametrize("language", ["en", "it"])
def test_area_detail_shows_a_distinct_translated_expired_update_state(
    page: Page, base_url: str, language: str
) -> None:
    _open_map(page, base_url, language=language)
    armed = False
    refresh_requested = False
    area_requests = 0
    detail_requests: list[dict[str, list[str]]] = []

    def expired_route(route: Route) -> None:
        nonlocal area_requests
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        square_id = parsed.path.rsplit("/", 1)[-1]
        target_date = query.get("target_date", [TARGET_DATES[0]])[0]
        update_id = query.get("update_id", [""])[0] or "update-current"
        if square_id == "cell-zero" and target_date == TARGET_DATES[0]:
            detail_requests.append(query)
        if armed and not refresh_requested and square_id == "cell-zero" and target_date == TARGET_DATES[0]:
            area_requests += 1
            route.fulfill(
                status=410,
                content_type="application/json",
                body=json.dumps({
                    "code": "update_expired",
                    "message_key": "area.update_expired",
                }),
            )
            return
        route.fulfill(
            content_type="application/json",
            body=json.dumps(_full_area_response(
                cell_id=square_id,
                target_date=target_date,
                update_id="update-new" if refresh_requested else update_id,
            )),
        )

    page.route("**/api/v1/areas/**", expired_route)
    def refreshed_squares_route(route: Route) -> None:
        parsed = urlparse(route.request.url)
        target_date = parse_qs(parsed.query).get("target_date", [TARGET_DATES[0]])[0]
        response = _squares_response(target_date)
        if refresh_requested:
            for feature in response["features"]:
                if feature["properties"].get("cell_id") == "cell-zero":
                    feature["properties"]["update_id"] = "update-new"
        route.fulfill(content_type="application/json", body=json.dumps(response))

    page.route("**/api/v1/squares**", refreshed_squares_route)
    page.wait_for_timeout(500)
    armed = True
    _click_square(page)
    detail = page.locator("aside[data-live-details]")
    expect(detail).to_contain_text(
        "Questo aggiornamento salvato è scaduto" if language == "it" else "This stored update has expired",
        timeout=10_000,
    )
    expect(detail).not_to_contain_text("The request failed")
    expect(detail.locator(".callout button")).to_contain_text(
        "Aggiorna la mappa" if language == "it" else "Refresh map"
    )
    expect(detail.locator(".callout button")).not_to_contain_text(
        "Riprova" if language == "it" else "Try again"
    )
    settled_requests = area_requests
    page.wait_for_timeout(500)
    assert area_requests == settled_requests
    refresh_requested = True
    detail.locator(".callout button").click()
    expect(detail).to_contain_text("12,5 mm" if language == "it" else "12.5 mm", timeout=10_000)
    expect(detail).not_to_contain_text(
        "Questo aggiornamento salvato è scaduto" if language == "it" else "This stored update has expired"
    )
    expect(page.locator("[data-map-app]")).to_have_attribute("data-update-id", "update-new")
    assert any(query.get("update_id") == ["update-new"] for query in detail_requests)


@pytest.mark.parametrize("language", ["en", "it"])
@pytest.mark.parametrize(
    ("reason", "english_text", "italian_text"),
    [
        (
            "older_rain",
            "No estimate is available because the earlier rain period is incomplete.",
            "Nessuna stima disponibile perché il periodo di pioggia precedente è incompleto.",
        ),
        (
            "reference_altitude",
            "No estimate is available because the weather reference altitude is missing.",
            "Nessuna stima disponibile perché manca l'altitudine di riferimento meteo.",
        ),
    ],
)
def test_area_detail_translates_supported_unavailable_reasons(
    page: Page,
    base_url: str,
    language: str,
    reason: str,
    english_text: str,
    italian_text: str,
) -> None:
    _open_map(page, base_url, language=language)
    _install_detail_route(
        page,
        unavailable_reason_by_date={TARGET_DATES[0]: reason},
    )
    _click_square(page)
    detail = page.locator("aside[data-live-details]")
    expect(detail).to_contain_text(italian_text if language == "it" else english_text, timeout=10_000)
    expect(detail).not_to_contain_text(reason)
    expect(detail).not_to_contain_text("Loading")


@pytest.mark.parametrize("language", ["en", "it"])
@pytest.mark.parametrize(
    ("reason", "english_text", "italian_text"),
    [
        (
            "pending",
            "The estimate is still being prepared",
            "La stima è ancora in preparazione",
        ),
        (
            "provider_unavailable",
            "The weather service is unavailable",
            "Il servizio meteo non è disponibile",
        ),
    ],
)
def test_area_detail_uses_map_reason_when_terminal_error_is_generic(
    page: Page,
    base_url: str,
    language: str,
    reason: str,
    english_text: str,
    italian_text: str,
) -> None:
    _open_map(page, base_url, language=language)

    def reason_map_route(route: Route) -> None:
        parsed = urlparse(route.request.url)
        target_date = parse_qs(parsed.query).get("target_date", [TARGET_DATES[0]])[0]
        response = _squares_response(target_date)
        for feature in response["features"]:
            if feature["properties"].get("cell_id") == "cell-zero":
                feature["properties"].update({
                    "state": "unavailable",
                    "percentage": None,
                    "reason": reason,
                    "unavailable_reason": reason,
                })
        route.fulfill(content_type="application/json", body=json.dumps(response))

    def reason_detail_route(route: Route) -> None:
        route.fulfill(
            status=409,
            content_type="application/json",
            body=json.dumps({"code": "estimate_not_available", "message_key": "estimate.unavailable"}),
        )

    page.route("**/api/v1/squares**", reason_map_route)
    page.route("**/api/v1/areas/**", reason_detail_route)
    # The map already holds the first response, so another date loads the changed one.
    page.locator(f".date-btn[data-date='{TARGET_DATES[1]}']").click()
    _wait_for_map_settled(page, TARGET_DATES[1])
    _click_square(page)
    detail = page.locator("aside[data-live-details]")
    expect(detail).to_contain_text(italian_text if language == "it" else english_text, timeout=10_000)
    expect(detail).not_to_contain_text("estimate_not_available")
    expect(detail).not_to_contain_text("Loading")


@pytest.mark.parametrize("language", ["en", "it"])
def test_area_detail_renders_host_source_provenance_and_quality(
    page: Page, base_url: str, language: str
) -> None:
    _open_map(page, base_url, language=language)
    _install_detail_route(page, host_facts=True, missing_host_factor=True)
    _click_square(page)
    detail = page.locator("aside[data-live-details]")
    expect(detail).to_contain_text("2006")
    resolution = re.compile(r"1[.\u00a0\u202f]?000,0 m") if language == "it" else "1,000.0 m"
    expect(detail).to_contain_text(resolution)
    expect(detail).to_contain_text("JRC")
    expect(detail).to_contain_text(
        "Presenza modellata" if language == "it" else "Modelled host occurrence"
    )
    expect(detail).to_contain_text(
        "non copertura arborea" if language == "it" else "not tree cover"
    )
    expect(detail).to_contain_text(
        "Manca la presenza" if language == "it" else "Host occurrence is missing"
    )


@pytest.mark.parametrize("language", ["en", "it"])
def test_area_detail_renders_weather_gap_metadata_without_inventing_totals(
    page: Page, base_url: str, language: str
) -> None:
    _open_map(page, base_url, language=language)
    _install_detail_route(
        page,
        weather_gaps=[
            {
                "date": TARGET_DATES[0],
                "variable": "precipitation",
                "reason_key": "missing_hour",
                "unit": "mm",
                "expected_hours": 24,
                "present_hours": 23,
            },
            {
                "date": TARGET_DATES[0],
                "variable": "soil_moisture",
                "reason_key": "missing_hour",
                "unit": "m3_m3",
                "expected_hours": 24,
                "present_hours": 23,
            },
        ],
    )
    _click_square(page)
    detail = page.locator("aside[data-live-details]")
    expect(detail).to_contain_text("12 October 2026" if language == "en" else "12 ottobre 2026")
    expect(detail).to_contain_text("Precipitation" if language == "en" else "Precipitazione")
    expect(detail).to_contain_text("m³/m³")
    expect(detail).to_contain_text("24")
    expect(detail).to_contain_text("23")
    expect(detail).to_contain_text(
        "stored weather hours" if language == "en" else "ore meteo salvate"
    )


@pytest.mark.parametrize("language", ["en", "it"])
def test_area_detail_distinguishes_missing_optional_and_old_states_and_close_focus(
    page: Page, base_url: str, language: str
) -> None:
    _open_map(page, base_url, language=language)
    _install_detail_route(page, optional_gap=True)
    _click_square(page)
    page.wait_for_function("() => Boolean(document.querySelector('[data-detail-experimental]'))")
    expect(page.locator("aside[data-live-details]")).to_contain_text(
        "Questo valore meteo opzionale è assente" if language == "it" else "This optional weather value is absent"
    )
    page.keyboard.press("Escape")
    expect(page.locator("aside[data-live-details]")).to_have_count(0)
    expect(page.locator("#map")).to_be_focused()
    expect(page.locator(".date-btn[aria-pressed='true']")).to_have_attribute("data-date", "2026-10-12")

    _click_square(page, "cell-missing")
    expect(page.locator("aside[data-live-details]")).to_contain_text(
        "dati obbligatori" if language == "it" else "required data"
    )


@pytest.mark.parametrize("viewport", [(1440, 900), (390, 844), (320, 568)])
def test_area_detail_sheet_stays_inside_supported_viewports(
    page: Page, base_url: str, viewport: tuple[int, int]
) -> None:
    _open_map(page, base_url, viewport=viewport)
    _install_detail_route(page)
    _click_square(page)
    page.wait_for_function("() => Boolean(document.querySelector('[data-detail-experimental]'))")
    box = page.locator("aside[data-live-details]").bounding_box()
    assert box
    assert box["x"] >= 0
    assert box["x"] + box["width"] <= viewport[0] + 1
    expect(page.locator("aside[data-live-details] #details-heading")).to_be_visible()
    expect(page.locator("aside[data-live-details] .live-details-close")).to_be_visible()
    height_control = page.locator("aside[data-live-details] [data-sheet-height]")
    if viewport[0] < 900:
        expect(height_control).to_be_visible()
    else:
        expect(height_control).to_be_hidden()
    favorite = page.locator("aside[data-live-details] [data-save]")
    expect(favorite).to_have_accessible_name("Save favorite")
    expect(favorite.locator("svg")).to_be_visible()
    assert favorite.inner_text() == ""


def test_area_detail_destination_events_keep_map_points_and_api_representatives(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    _install_detail_route(page)
    page.evaluate(
        """() => {
          window.__areaDetailSelectionEvents = [];
          window.addEventListener('micometeo:selectionchange', (event) => {
            window.__areaDetailSelectionEvents.push(event.detail);
          });
        }"""
    )
    _click_square(page)
    page.wait_for_function("() => Boolean(document.querySelector('[data-detail-experimental]'))")
    events = page.evaluate("() => window.__areaDetailSelectionEvents")
    map_event = next(event for event in reversed(events) if event.get("source") == "map")
    assert map_event["point"]["latitude"] == pytest.approx(44.13, abs=0.00001)
    assert map_event["point"]["longitude"] == pytest.approx(10.64, abs=0.00001)
    assert map_event["destination"] == map_event["point"]

    page.evaluate(
        "() => window.MicometeoMap.map.jumpTo({center: [10.64, 44.13], zoom: 12})"
    )
    page.wait_for_function(
        """() => {
          const map = window.MicometeoMap.map;
          const point = map.project([10.64, 44.13]);
          return map.queryRenderedFeatures(point, {
            layers: ['micometeo-square-estimates', 'micometeo-square-missing'],
          }).some((feature) => feature.properties?.cell_id === 'cell-zero');
        }""",
        timeout=10_000,
    )
    page.locator("#centre-btn").click()
    page.wait_for_function(
        "() => document.querySelector('aside[data-live-details]')?.textContent.includes('44.1312')",
        timeout=10_000,
    )
    events = page.evaluate("() => window.__areaDetailSelectionEvents")
    centre_event = next(event for event in reversed(events) if event.get("source") == "centre")
    assert centre_event["point"] is None
    assert centre_event["representative"] == {"latitude": 44.1312, "longitude": 10.6413}
    assert centre_event["destination"] == centre_event["representative"]
    assert centre_event["destination"] != {"latitude": 44.13, "longitude": 10.64}


def test_area_detail_keyboard_rain_switch_restores_focus_and_phone_height_changes(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url, viewport=(390, 844))
    _install_detail_route(page)
    _click_square(page)
    page.wait_for_function("() => Boolean(document.querySelector('[data-detail-experimental]'))")
    detail = page.locator("aside[data-live-details]")
    rain_button = detail.locator("[data-rain-days='14']")
    rain_button.focus()
    page.keyboard.press("Enter")
    expect(rain_button).to_be_focused()
    expect(detail.locator(".detail-rain-value")).to_contain_text("24.5 mm")

    height_button = detail.locator("[data-sheet-height]")
    expect(detail).to_have_attribute("data-size", "short")
    height_button.click()
    expect(detail).to_have_attribute("data-size", "half")
    height_button.click()
    expect(detail).to_have_attribute("data-size", "tall")
