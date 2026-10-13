from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page, Route, expect

from tests.e2e.test_area_details import _click_square, _full_area_response, _install_detail_route
from tests.e2e.test_favorites import _favorite_item, _open_favorites, _save_selected, _set_storage
from tests.e2e.test_map_controls import TARGET_DATES, _open_map


def _wait_for_navigation_builder(page: Page) -> None:
    page.wait_for_function("() => Boolean(window.MicometeoNavigation?.buildGoogleMapsUrl)")


def test_google_maps_url_builder_validates_coordinates_and_keeps_precision(
    page: Page, base_url: str
) -> None:
    page.goto(url=f"{base_url}/map/fixture/ready/", wait_until="domcontentloaded")
    _wait_for_navigation_builder(page)
    values = page.evaluate(
        """
        () => {
          const build = window.MicometeoNavigation.buildGoogleMapsUrl;
          return {
            point: build({latitude: 44.131200123, longitude: -10.641300987}),
            edge: build({latitude: 90, longitude: -180}),
            missing: build({latitude: 44.13}),
            text: build({latitude: '44.13', longitude: 10.64}),
            nan: build({latitude: NaN, longitude: 10.64}),
            infinite: build({latitude: 44.13, longitude: Infinity}),
            latitude: build({latitude: 90.1, longitude: 10.64}),
            longitude: build({latitude: 44.13, longitude: -180.1}),
          };
        }
        """
    )
    assert values["point"] == (
        "https://www.google.com/maps/search/?api=1&query=44.131200123%2C-10.641300987"
    )
    assert values["edge"] == "https://www.google.com/maps/search/?api=1&query=90%2C-180"
    for key in ("missing", "text", "nan", "infinite", "latitude", "longitude"):
        assert values[key] is None
    assert "44.131200123" in values["point"]
    assert "-10.641300987" in values["point"]
    assert "name" not in values["point"]


def test_fixture_navigation_stays_disabled_in_english_and_italian(
    page: Page, base_url: str
) -> None:
    for language, label in (("en", "Open in Google Maps"), ("it", "Apri in Google Maps")):
        page.set_extra_http_headers(
            {"Accept-Language": "it-IT,it;q=0.9" if language == "it" else "en-GB,en;q=0.9"}
        )
        page.goto(
            url=f"{base_url}/map/fixture/ready/?lang={language}",
            wait_until="domcontentloaded",
        )
        action = page.locator("[data-navigation]")
        expect(action).to_be_disabled()
        expect(action).to_have_text(label)
        expect(page.locator("[data-navigation-status]")).to_be_visible()
        expect(page.locator("[data-navigation-status]")).not_to_contain_text(
            "parking" if language == "en" else "parcheggio"
        )


def test_point_navigation_uses_exact_selection_after_map_and_date_changes(
    page: Page, base_url: str
) -> None:
    _open_map(page=page, base_url=base_url)
    _install_detail_route(page=page)
    _click_square(page=page)
    action = page.locator("aside[data-live-details] [data-navigation]")
    expect(action).to_be_enabled()
    expected = page.evaluate(
        """
        () => window.MicometeoNavigation.buildGoogleMapsUrl({
          latitude: Number(document.querySelector('[data-map-app]').dataset.pointLatitude),
          longitude: Number(document.querySelector('[data-map-app]').dataset.pointLongitude),
        })
        """
    )
    expect(action).to_have_attribute("data-navigation-url", expected)

    page.evaluate("() => window.MicometeoMap.map.jumpTo({center: [11.1, 44.5], zoom: 12})")
    page.locator(f".date-btn[data-date='{TARGET_DATES[1]}']").click()
    expect(action).to_have_attribute("data-navigation-url", expected)

    external_requests: list[str] = []

    def external_route(route: Route) -> None:
        external_requests.append(route.request.url)
        route.fulfill(status=200, content_type="text/html", body="<title>Google Maps fixture</title>")

    page.context.route("https://www.google.com/maps/search/**", external_route)
    assert external_requests == []
    with page.expect_popup() as popup_info:
        action.click()
    popup = popup_info.value
    assert external_requests == [expected]
    assert popup.url == expected


def test_grid_navigation_waits_for_verified_area_representative(
    page: Page, base_url: str
) -> None:
    _open_map(page=page, base_url=base_url)
    _install_detail_route(page=page)
    _click_square(page=page)
    action = page.locator("aside[data-live-details] [data-navigation]")
    expect(action).to_be_visible()
    expect(action).to_be_enabled()
    page.evaluate(
        "() => window.MicometeoMap.map.jumpTo({center: [10.64, 44.13], zoom: 12})"
    )
    page.wait_for_function(
        """
        () => {
          const map = window.MicometeoMap.map;
          const point = map.project([10.64, 44.13]);
          return map.queryRenderedFeatures(point, {
            layers: ['micometeo-square-estimates', 'micometeo-square-missing'],
          }).some((feature) => feature.properties?.cell_id === 'cell-zero');
        }
        """
    )
    page.locator("#centre-btn").click()
    expect(action).to_be_enabled()
    expect(action).to_have_attribute(
        "data-navigation-url",
        "https://www.google.com/maps/search/?api=1&query=44.1312%2C10.6413",
    )
    expect(page.locator("[data-navigation-status]")).to_contain_text(
        "representative point"
    )


def test_grid_navigation_does_not_reuse_stale_representative(
    page: Page, base_url: str
) -> None:
    _open_map(page=page, base_url=base_url)
    requests: list[str] = []

    def detail_route(route: Route) -> None:
        query = parse_qs(urlparse(route.request.url).query)
        target_date = query["target_date"][0]
        requests.append(target_date)
        response = _full_area_response(cell_id="cell-zero", target_date=target_date)
        if target_date == TARGET_DATES[1]:
            response["selection"].pop("representative_coordinates", None)
        route.fulfill(content_type="application/json", body=json.dumps(response))

    page.route("**/api/v1/areas/**", detail_route)
    _click_square(page=page)
    action = page.locator("aside[data-live-details] [data-navigation]")
    expect(action).to_be_enabled()
    page.evaluate(
        "() => window.MicometeoMap.map.jumpTo({center: [10.64, 44.13], zoom: 12})"
    )
    page.wait_for_function(
        """
        () => {
          const map = window.MicometeoMap.map;
          const point = map.project([10.64, 44.13]);
          return map.queryRenderedFeatures(point, {
            layers: ['micometeo-square-estimates', 'micometeo-square-missing'],
          }).some((feature) => feature.properties?.cell_id === 'cell-zero');
        }
        """
    )
    page.locator("#centre-btn").click()
    expect(action).to_have_attribute(
        "data-navigation-url",
        "https://www.google.com/maps/search/?api=1&query=44.1312%2C10.6413",
    )
    page.locator(f".date-btn[data-date='{TARGET_DATES[1]}']").click()
    page.wait_for_function(
        """() => document.querySelector('[data-navigation]')?.dataset.navigationUrl === ''"""
    )
    expect(action).to_be_disabled()
    assert TARGET_DATES[1] in requests


def test_grid_navigation_rejects_out_of_range_representative(
    page: Page, base_url: str
) -> None:
    _open_map(page=page, base_url=base_url)

    def detail_route(route: Route) -> None:
        query = parse_qs(urlparse(route.request.url).query)
        response = _full_area_response(
            cell_id="cell-zero",
            target_date=query["target_date"][0],
        )
        response["selection"]["representative_coordinates"] = {
            "latitude": 91,
            "longitude": 10.6413,
        }
        route.fulfill(content_type="application/json", body=json.dumps(response))

    page.route("**/api/v1/areas/**", detail_route)
    _click_square(page=page)
    page.evaluate(
        "() => window.MicometeoMap.map.jumpTo({center: [10.64, 44.13], zoom: 12})"
    )
    page.wait_for_function(
        """
        () => {
          const map = window.MicometeoMap.map;
          const point = map.project([10.64, 44.13]);
          return map.queryRenderedFeatures(point, {
            layers: ['micometeo-square-estimates', 'micometeo-square-missing'],
          }).some((feature) => feature.properties?.cell_id === 'cell-zero');
        }
        """
    )
    page.locator("#centre-btn").click()
    action = page.locator("aside[data-live-details] [data-navigation]")
    expect(action).to_be_disabled()
    expect(page.locator("[data-navigation-status]")).to_be_visible()


def test_grid_favorite_waits_for_current_representative_before_enabling_navigation(
    page: Page, base_url: str
) -> None:
    _open_map(page=page, base_url=base_url)
    pending: list[Route] = []

    def detail_route(route: Route) -> None:
        pending.append(route)

    page.route("**/api/v1/areas/**", detail_route)
    _set_storage(
        page=page,
        value={
            "version": 1,
            "items": [
                _favorite_item(
                    favorite_id="favorite-grid",
                    kind="grid",
                    latitude=44.13,
                    longitude=10.64,
                    name="Saved grid",
                    cell_id="cell-zero",
                )
            ],
        },
    )
    _open_favorites(page=page)
    page.locator("[data-favorite-id]").locator("[data-favorite-open]").click()
    action = page.locator("aside[data-live-details] [data-navigation]")
    expect(action).to_be_visible()
    expect(action).to_be_disabled()
    assert pending
    response = _full_area_response(cell_id="cell-zero", target_date=TARGET_DATES[0])
    for route in pending:
        route.fulfill(content_type="application/json", body=json.dumps(response))
    expect(action).to_be_enabled()
    expect(action).to_have_attribute(
        "data-navigation-url",
        "https://www.google.com/maps/search/?api=1&query=44.1312%2C10.6413",
    )


def test_unsafe_favorite_name_stays_text_and_cannot_change_navigation_url(
    page: Page, base_url: str
) -> None:
    _open_map(page=page, base_url=base_url)
    _install_detail_route(page=page)
    _click_square(page=page)
    unsafe_name = "<img src=x onerror=alert(1)>"
    _save_selected(page=page, name=unsafe_name)
    _open_favorites(page=page)
    card = page.locator("[data-favorite-id]").first
    expect(card.locator("h3")).to_have_text(unsafe_name)
    assert card.locator("img").count() == 0
    card.locator("[data-favorite-open]").click()
    action = page.locator("aside[data-live-details] [data-navigation]")
    expect(action).to_be_enabled()
    url = action.get_attribute("data-navigation-url") or ""
    assert url.startswith("https://www.google.com/maps/search/?api=1&query=")
    assert unsafe_name not in url
    assert "javascript:" not in url
