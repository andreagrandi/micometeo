from __future__ import annotations

import json
from math import isclose
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, Route, expect

from tests.e2e.test_area_details import _click_square
from tests.e2e.test_map_controls import (
    TARGET_DATES,
    _area_response,
    _open_map,
)


STORAGE_KEY = "micometeo.favorites"
GRID_CENTER = {"latitude": 44.13, "longitude": 10.64}
POINT_CENTER = {"latitude": 44.1305, "longitude": 10.6405}


def _wait_for_live_map(page: Page) -> None:
    page.wait_for_function("() => Boolean(window.MicometeoMap?.map?.getSource?.('squares'))")


def _open_favorites(page: Page) -> None:
    page.locator("[data-favourites]").click()
    expect(page.locator("[data-favorites-dialog]")).to_be_visible()


def _save_selected(page: Page, *, name: str, color: str | None = None) -> None:
    page.locator("[data-save]").first.click()
    form = page.locator("form.favorite-form")
    expect(form).to_be_visible()
    form.locator("[data-favorite-name]").fill(name)
    if color is not None:
        form.locator("[data-favorite-color]").select_option(color)
    form.locator("button[type='submit']").click()
    if page.locator("[data-favorite-close]").count():
        page.locator("[data-favorite-close]").click()


def _save_favorite_from_list(page: Page, *, name: str, color: str | None = None) -> None:
    page.locator("[data-favorite-save-selected]").click()
    form = page.locator("form.favorite-form")
    expect(form).to_be_visible()
    form.locator("[data-favorite-name]").fill(name)
    if color is not None:
        form.locator("[data-favorite-color]").select_option(color)
    form.locator("button[type='submit']").click()


def _set_storage(page: Page, value: object) -> str:
    raw = json.dumps(value, separators=(",", ":"))
    page.evaluate(
        "([key, value]) => window.localStorage.setItem(key, value)",
        [STORAGE_KEY, raw],
    )
    return raw


def _read_storage(page: Page) -> dict[str, object]:
    return page.evaluate("key => JSON.parse(window.localStorage.getItem(key))", STORAGE_KEY)


def _point_routes(page: Page, *, square_id: str = "cell-zero") -> list[dict[str, object]]:
    requests: list[dict[str, object]] = []

    def search_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "results": [
                        {
                            "name": "Pistoia point",
                            "context": "Pistoia, Toscana",
                            "latitude": POINT_CENTER["latitude"],
                            "longitude": POINT_CENTER["longitude"],
                        }
                    ],
                    "cached": False,
                }
            ),
        )

    def resolve_route(route: Route) -> None:
        payload = route.request.post_data_json
        assert isinstance(payload, dict)
        requests.append(
            {
                "payload": payload,
                "headers": dict(route.request.headers),
                "url": route.request.url,
            }
        )
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "status": "ok",
                    "point": POINT_CENTER,
                    "representative": GRID_CENTER,
                    "square_id": square_id,
                    "region": "Pistoia",
                }
            ),
        )

    page.route("**/api/v1/places/search**", search_route)
    page.route("**/api/v1/places/resolve**", resolve_route)
    return requests


def _select_search_point(page: Page) -> None:
    search = page.locator("[data-place-search]")
    search.fill("Pistoia")
    expect(page.locator("[data-search-results] [role=option]")).to_have_count(1)
    search.press("ArrowDown")
    search.press("Enter")
    page.wait_for_function(
        "() => document.querySelector('[data-map-app]').dataset.selectionSource === 'search'"
    )


def _favorite_item(
    *,
    favorite_id: str,
    kind: str,
    latitude: float,
    longitude: float,
    name: str,
    cell_id: str | None = None,
    color: str | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "id": favorite_id,
        "kind": kind,
        "latitude": latitude,
        "longitude": longitude,
        "name": name,
    }
    if cell_id is not None:
        item["cellId"] = cell_id
    if color is not None:
        item["color"] = color
    return item


def _assert_no_private_metadata(
    requests: list[tuple[str, str, str]], items: list[dict[str, object]]
) -> None:
    transmitted = "\n".join(value for request in requests for value in request)
    assert STORAGE_KEY not in transmitted
    for item in items:
        for key in ("id", "name", "color"):
            value = item.get(key)
            if value:
                assert str(value) not in transmitted


@pytest.mark.parametrize(
    ("language", "viewport", "notice"),
    [
        ("en", (1440, 900), "Favorites stay in this browser"),
        ("it", (390, 844), "I preferiti restano in questo browser"),
        ("en", (2560, 900), "Favorites stay in this browser"),
    ],
)
def test_favorites_add_point_and_grid_reload_and_reopen(
    page: Page,
    base_url: str,
    language: str,
    viewport: tuple[int, int],
    notice: str,
) -> None:
    requests: list[tuple[str, str, str]] = []
    page.on(
        "request",
        lambda request: requests.append(
            (request.url, request.post_data or "", json.dumps(request.headers))
        ),
    )
    _point_routes(page, square_id="")
    _open_map(page, base_url, language=language, viewport=viewport)
    page.evaluate("key => window.localStorage.removeItem(key)", STORAGE_KEY)

    _click_square(page, "cell-zero")
    expect(page.locator("aside[data-live-details] [data-save]")).to_be_visible()
    _save_selected(page, name="Abetone <north>", color="green")

    _select_search_point(page)
    _open_favorites(page)
    _save_favorite_from_list(page, name="Pistoia point", color="blue")

    stored = _read_storage(page)
    assert stored["version"] == 1
    assert {item["kind"] for item in stored["items"]} == {"grid", "point"}
    stored_items = [dict(item) for item in stored["items"]]
    _assert_no_private_metadata(requests, stored_items)
    expect(page.locator("[data-favorites-dialog] .favorites-note")).to_contain_text(notice)

    page.reload(wait_until="domcontentloaded")
    _wait_for_live_map(page)
    _open_favorites(page)
    expect(page.locator("[data-favorite-id]")).to_have_count(2)
    grid_card = page.locator("[data-favorite-id]").filter(has_text="Abetone <north>")
    point_card = page.locator("[data-favorite-id]").filter(has_text="Pistoia point")
    expect(grid_card).to_have_attribute("data-favorite-color", "green")
    expect(point_card).to_have_attribute("data-favorite-color", "blue")
    expect(grid_card.locator("h3")).to_have_text("Abetone <north>")

    point_card.locator("[data-favorite-open]").click()
    page.wait_for_function(
        "() => document.querySelector('[data-map-app]').dataset.selectionSource === 'point'"
    )
    expect(page.locator("[data-map-app]")).to_have_attribute("data-point-latitude", "44.1305")
    assert requests[-1][0].endswith("/api/v1/places/resolve")

    _open_favorites(page)
    grid_request_start = len(requests)
    page.locator("[data-favorite-id]").filter(has_text="Abetone <north>").locator(
        "[data-favorite-open]"
    ).click()
    expect(page.locator("aside[data-live-details] h2")).to_have_text("cell-zero")
    grid_requests = requests[grid_request_start:]
    _assert_no_private_metadata(
        grid_requests, [item for item in stored_items if item["kind"] == "grid"]
    )
    assert "favorite" not in page.url.lower()
    for item in stored_items:
        for key in ("id", "name", "color"):
            value = item.get(key)
            if value:
                assert str(value) not in page.url
    assert "favorite" not in "\n".join(
        value for request in grid_requests for value in request
    ).lower()
    _assert_no_private_metadata(requests, stored_items)


def test_favorites_dialog_fills_768px_phone_viewport(page: Page, base_url: str) -> None:
    _open_map(page, base_url, viewport=(768, 900))
    _open_favorites(page)
    dialog = page.locator("[data-favorites-dialog]")
    bounds = dialog.evaluate(
        """element => {
          const rect = element.getBoundingClientRect();
          return {left: rect.left, right: rect.right, width: rect.width};
        }"""
    )
    viewport_width = page.evaluate("() => window.innerWidth")
    assert isclose(bounds["left"], 0, abs_tol=1)
    assert isclose(bounds["right"], viewport_width, abs_tol=1)
    assert isclose(bounds["width"], viewport_width, abs_tol=1)


def test_favorites_duplicate_edit_remove_and_optional_color_persist_after_reload(
    page: Page, base_url: str
) -> None:
    requests: list[tuple[str, str, str]] = []
    page.on(
        "request",
        lambda request: requests.append(
            (request.url, request.post_data or "", json.dumps(request.headers))
        ),
    )
    _open_map(page, base_url)
    page.evaluate("key => window.localStorage.removeItem(key)", STORAGE_KEY)
    _click_square(page, "cell-zero")
    _save_selected(page, name="Original square", color="amber")

    _save_selected(page, name="Duplicate square", color="rose")
    expect(page.locator("[data-toast]")).to_contain_text("already")
    stored = _read_storage(page)
    assert len(stored["items"]) == 1
    assert stored["items"][0]["name"] == "Original square"
    metadata_items = [dict(stored["items"][0])]

    _open_favorites(page)
    page.locator("[data-favorite-edit]").click()
    form = page.locator("form.favorite-form")
    form.locator("[data-favorite-name]").fill("Renamed square")
    form.locator("[data-favorite-color]").select_option("")
    form.locator("button[type='submit']").click()
    updated = _read_storage(page)
    assert updated["items"][0]["name"] == "Renamed square"
    assert "color" not in updated["items"][0]
    metadata_items.append(dict(updated["items"][0]))

    page.reload(wait_until="domcontentloaded")
    _wait_for_live_map(page)
    _open_favorites(page)
    expect(page.locator("[data-favorite-id]")).to_have_count(1)
    expect(page.locator("[data-favorite-id] h3")).to_have_text("Renamed square")
    page.locator("[data-favorite-remove]").click()
    page.reload(wait_until="domcontentloaded")
    _wait_for_live_map(page)
    _open_favorites(page)
    expect(page.locator("[data-favorites-dialog] .favorites-empty")).to_be_visible()
    _assert_no_private_metadata(requests, metadata_items)


def test_favorites_reopen_point_uses_current_result_and_point_source(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    area_requests: list[str] = []
    resolve_requests = _point_routes(page, square_id="cell-zero")

    def area_route(route: Route) -> None:
        area_requests.append(route.request.url)
        parsed = urlparse(route.request.url)
        cell_id = parsed.path.rsplit("/", 1)[-1]
        body = _area_response(
            cell_id=cell_id,
            target_date="2026-10-12",
            update_id="update-current",
        )
        body["estimate"]["whole_percentage"] = 73
        route.fulfill(content_type="application/json", body=json.dumps(body))

    page.route("**/api/v1/areas/**", area_route)
    _set_storage(
        page,
        {
            "version": 1,
            "items": [
                {
                    "id": "saved-point",
                    "kind": "point",
                    "latitude": 44.1305,
                    "longitude": 10.6405,
                    "name": "Saved point",
                }
            ],
        },
    )
    assert page.evaluate("() => window.MicometeoFavorites.read().items.length") == 1
    _open_favorites(page)
    page.locator("[data-favorite-open]").click()
    expect(page.locator("aside[data-live-details] h2")).to_have_text("cell-zero")
    expect(page.locator("aside[data-live-details]")).to_contain_text("73%")
    assert resolve_requests
    assert resolve_requests[-1]["payload"] == {
        "latitude": 44.1305,
        "longitude": 10.6405,
        "source": "point",
    }
    assert area_requests
    assert all("saved-point" not in request for request in area_requests)
    assert all("percentage" not in request for request in area_requests)


def test_favorites_point_wins_over_delayed_geolocation_callback(
    page: Page, base_url: str
) -> None:
    page.add_init_script(
        """
        window.__pendingLocation = null;
        navigator.geolocation.getCurrentPosition = (success, failure) => {
          window.__pendingLocation = {success, failure};
        };
        """
    )
    resolve_requests = _point_routes(page, square_id="cell-zero")
    _open_map(page, base_url)
    page.locator("[data-location]").click()
    page.wait_for_function("() => window.__pendingLocation?.success")
    _set_storage(
        page,
        {
            "version": 1,
            "items": [
                _favorite_item(
                    favorite_id="saved-point",
                    kind="point",
                    latitude=POINT_CENTER["latitude"],
                    longitude=POINT_CENTER["longitude"],
                    name="Saved point",
                )
            ],
        },
    )

    _open_favorites(page)
    page.locator("[data-favorite-open]").click()
    expect(page.locator("aside[data-live-details] h2")).to_have_text("cell-zero")
    expect(page.locator("[data-map-app]")).to_have_attribute(
        "data-point-latitude", str(POINT_CENTER["latitude"])
    )
    assert len(resolve_requests) == 1

    page.evaluate(
        "() => window.__pendingLocation.success({coords: {latitude: 43.93, longitude: 10.92}})"
    )
    expect(page.locator("[data-map-app]")).to_have_attribute(
        "data-selection-source", "point"
    )
    expect(page.locator("[data-map-app]")).to_have_attribute(
        "data-point-latitude", str(POINT_CENTER["latitude"])
    )
    expect(page.locator("[data-map-app]")).to_have_attribute(
        "data-point-longitude", str(POINT_CENTER["longitude"])
    )
    assert len(resolve_requests) == 1


def test_grid_favorite_selects_exact_fresh_cell_and_does_not_use_neighbor(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    page.evaluate(
        """key => window.localStorage.setItem(key, JSON.stringify({
          version: 1,
          items: [{
            id: 'fresh-cell', kind: 'grid', latitude: 44.13, longitude: 10.645,
            cellId: 'cell-hundred', name: 'Fresh cell'
          }]
        }))""",
        STORAGE_KEY,
    )
    area_requests: list[str] = []

    def area_route(route: Route) -> None:
        area_requests.append(route.request.url)
        parsed = urlparse(route.request.url)
        cell_id = parsed.path.rsplit("/", 1)[-1]
        route.fulfill(
            content_type="application/json",
            body=json.dumps(
                _area_response(
                    cell_id=cell_id,
                    target_date="2026-10-12",
                    update_id="update-current",
                )
            ),
        )

    page.route("**/api/v1/areas/**", area_route)
    _open_favorites(page)
    page.locator("[data-favorite-open]").click()
    expect(page.locator("aside[data-live-details] h2")).to_have_text("cell-hundred")
    assert any("/api/v1/areas/cell-hundred" in request for request in area_requests)
    assert all("/api/v1/areas/cell-zero" not in request for request in area_requests)


def test_favorites_malformed_rows_keep_valid_entry_and_raw_invalid_data(
    page: Page, base_url: str
) -> None:
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url + (request.post_data or "")))
    _open_map(page, base_url)
    invalid = {
        "id": "bad",
        "kind": "point",
        "latitude": "44.1",
        "longitude": 10.6,
        "name": "<img src=x onerror=alert(1)>",
        "metadata_url": "https://attacker.invalid/private",
    }
    wrapper = {
        "version": 1,
        "items": [
            _favorite_item(
                favorite_id="good",
                kind="point",
                latitude=44.1,
                longitude=10.6,
                name="Good <b>point</b>",
            ),
            invalid,
        ],
    }
    raw = _set_storage(page, wrapper)
    page.reload(wait_until="domcontentloaded")
    _wait_for_live_map(page)
    _open_favorites(page)
    expect(page.locator("[data-favorites-dialog] .favorites-status")).to_contain_text("could not")
    expect(page.locator("[data-favorite-id]")).to_have_count(1)
    expect(page.locator("[data-favorite-id] h3")).to_have_text("Good <b>point</b>")
    assert page.locator("[data-favorite-id] script").count() == 0
    assert all("attacker.invalid" not in request for request in requests)

    page.locator("[data-favorite-edit]").click()
    page.locator("[data-favorite-name]").fill("Good renamed")
    page.locator("form.favorite-form button[type='submit']").click()
    stored = _read_storage(page)
    assert stored["items"][0]["name"] == "Good renamed"
    assert stored["items"][1] == invalid
    assert json.dumps(stored, separators=(",", ":")) != raw


def test_favorites_duplicate_ids_quarantine_all_rows_and_keep_unique_row_usable(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    duplicate_point = _favorite_item(
        favorite_id="shared-id",
        kind="point",
        latitude=44.13,
        longitude=10.64,
        name="Shared point",
    )
    duplicate_grid = _favorite_item(
        favorite_id="shared-id",
        kind="grid",
        latitude=44.14,
        longitude=10.65,
        cell_id="cell-hundred",
        name="Shared grid",
    )
    unrelated = _favorite_item(
        favorite_id="unrelated-id",
        kind="point",
        latitude=44.2,
        longitude=10.8,
        name="Unrelated point",
    )
    _set_storage(
        page,
        {"version": 1, "items": [duplicate_point, duplicate_grid, unrelated]},
    )
    page.reload(wait_until="domcontentloaded")
    _wait_for_live_map(page)
    _open_favorites(page)
    expect(page.locator("[data-favorites-dialog] .favorites-status")).to_contain_text("could not")
    expect(page.locator("[data-favorite-id]")).to_have_count(1)
    expect(page.locator("[data-favorite-id='shared-id']")).to_have_count(0)
    expect(page.locator("[data-favorite-id='unrelated-id'] h3")).to_have_text("Unrelated point")

    page.locator("[data-favorite-id='unrelated-id'] [data-favorite-edit]").click()
    page.locator("[data-favorite-name]").fill("Unrelated point edited")
    page.locator("form.favorite-form button[type='submit']").click()
    after_edit = _read_storage(page)
    assert duplicate_point in after_edit["items"]
    assert duplicate_grid in after_edit["items"]
    assert any(
        item.get("id") == "unrelated-id" and item.get("name") == "Unrelated point edited"
        for item in after_edit["items"]
    )
    assert after_edit["items"][-2:] == [duplicate_point, duplicate_grid]

    page.reload(wait_until="domcontentloaded")
    _wait_for_live_map(page)
    _open_favorites(page)
    expect(page.locator("[data-favorites-dialog] .favorites-status")).to_contain_text("could not")
    expect(page.locator("[data-favorite-id]")).to_have_count(1)
    expect(page.locator("[data-favorite-id='shared-id']")).to_have_count(0)
    expect(page.locator("[data-favorite-id='unrelated-id'] h3")).to_have_text(
        "Unrelated point edited"
    )

    page.locator("[data-favorite-id='unrelated-id'] [data-favorite-remove]").click()
    after_remove = _read_storage(page)
    assert after_remove["items"] == [duplicate_point, duplicate_grid]
    assert duplicate_grid in after_remove["items"]

    page.reload(wait_until="domcontentloaded")
    _wait_for_live_map(page)
    _open_favorites(page)
    expect(page.locator("[data-favorites-dialog] .favorites-status")).to_contain_text("could not")
    expect(page.locator("[data-favorite-id]")).to_have_count(0)
    expect(page.locator("[data-favorites-dialog] .favorites-empty")).to_be_visible()
    assert _read_storage(page)["items"] == [duplicate_point, duplicate_grid]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not-json", "could not be read"),
        (
            json.dumps(
                {
                    "version": 2,
                    "items": [
                        _favorite_item(
                            favorite_id="future",
                            kind="point",
                            latitude=44.1,
                            longitude=10.6,
                            name="Future format",
                        )
                    ],
                }
            ),
            "newer",
        ),
    ],
)
def test_favorites_invalid_or_future_storage_is_read_only(
    page: Page, base_url: str, raw: str, message: str
) -> None:
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url + (request.post_data or "")))
    _open_map(page, base_url)
    _click_square(page, "cell-zero")
    page.evaluate(
        "([key, value]) => window.localStorage.setItem(key, value)",
        [STORAGE_KEY, raw],
    )
    _open_favorites(page)
    expect(page.locator("[data-favorites-dialog] .favorites-status")).to_contain_text(message)
    page.locator("[data-favorite-save-selected]").click()
    page.locator("[data-favorite-name]").fill("Should not save")
    page.locator("form.favorite-form button[type='submit']").click()
    assert page.evaluate("key => window.localStorage.getItem(key)", STORAGE_KEY) == raw
    assert page.locator("#map canvas.maplibregl-canvas").is_visible()
    assert all("Should not save" not in request for request in requests)


def test_favorites_storage_getter_failure_warns_and_keeps_map_usable(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    page.evaluate(
        """() => Object.defineProperty(window, 'localStorage', {
          configurable: true,
          get() { throw new DOMException('blocked', 'SecurityError'); }
        })"""
    )
    _open_favorites(page)
    expect(page.locator("[data-favorites-dialog] .favorites-status")).to_contain_text("unavailable")
    expect(page.locator("#map canvas.maplibregl-canvas")).to_be_visible()


def test_favorites_quota_failure_does_not_change_add_edit_or_remove(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    _click_square(page, "cell-hundred")
    page.evaluate(
        """key => window.localStorage.setItem(key, JSON.stringify({
          version: 1,
          items: [{
            id: 'old', kind: 'grid', latitude: 44.13, longitude: 10.64,
            cellId: 'cell-zero', name: 'Old favorite', color: 'green'
          }]
        }))""",
        STORAGE_KEY,
    )
    page.evaluate(
        """() => {
          Storage.prototype.setItem = () => {
            throw new DOMException('full', 'QuotaExceededError');
          };
        }"""
    )

    _open_favorites(page)
    _save_favorite_from_list(page, name="New favorite", color="rose")
    expect(page.locator("[data-favorite-form-status]")).to_contain_text("full")
    page.locator("[data-favorite-close]").click()

    _open_favorites(page)
    page.locator("[data-favorite-edit]").click()
    page.locator("[data-favorite-name]").fill("Edited favorite")
    page.locator("form.favorite-form button[type='submit']").click()
    expect(page.locator("[data-favorite-form-status]")).to_contain_text("full")
    page.locator("[data-favorite-close]").click()

    _open_favorites(page)
    page.locator("[data-favorite-remove]").click()
    expect(page.locator("[data-favorite-form-status]")).to_contain_text("full")
    expect(page.locator("[data-favorite-id]")).to_have_count(1)
    stored = page.evaluate(
        "key => JSON.parse(window.localStorage.getItem(key))",
        STORAGE_KEY,
    )
    assert stored["items"][0]["name"] == "Old favorite"


def test_favorites_missing_weather_stays_saved_and_opens_unavailable_state(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    page.evaluate(
        """key => window.localStorage.setItem(key, JSON.stringify({
          version: 1,
          items: [{
            id: 'missing-weather', kind: 'grid', latitude: 44.13, longitude: 10.65,
            cellId: 'cell-missing', name: 'Missing weather'
          }]
        }))""",
        STORAGE_KEY,
    )

    def unavailable_area(route: Route) -> None:
        parsed = urlparse(route.request.url)
        cell_id = parsed.path.rsplit("/", 1)[-1]
        target_date = route.request.url.split("target_date=", 1)[-1].split("&", 1)[0]
        body = _area_response(
            cell_id=cell_id,
            target_date=target_date or TARGET_DATES[0],
            update_id="update-current",
        )
        body["estimate"].update(
            {"state": "unavailable", "whole_percentage": None, "unavailable_reason": "recent_rain"}
        )
        route.fulfill(content_type="application/json", body=json.dumps(body))

    page.route("**/api/v1/areas/**", unavailable_area)
    _open_favorites(page)
    page.locator("[data-favorite-open]").click()
    detail = page.locator("aside[data-live-details]")
    expect(detail.locator("h2")).to_have_text("cell-missing")
    expect(detail).to_contain_text("No estimate")
    _open_favorites(page)
    expect(page.locator("[data-favorite-id] h3")).to_have_text("Missing weather")


def test_favorites_missing_grid_cell_keeps_saved_location_without_neighbor(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    saved = {"latitude": 44.20, "longitude": 10.80}
    page.evaluate(
        "([key, value]) => window.localStorage.setItem(key, JSON.stringify(value))",
        [
            STORAGE_KEY,
            {
                "version": 1,
                "items": [
                    _favorite_item(
                        favorite_id="old-cell",
                        kind="grid",
                        latitude=saved["latitude"],
                        longitude=saved["longitude"],
                        cell_id="old-cell",
                        name="Old cell",
                    )
                ],
            },
        ],
    )
    _open_favorites(page)
    page.locator("[data-favorite-open]").click()
    expect(page.locator("aside[data-live-details] h2")).to_have_text("old-cell")
    expect(page.locator("aside[data-live-details]")).to_contain_text("not in the current map data")
    expect(page.locator("[data-map-app]")).to_have_attribute("data-point-latitude", "44.2")
    expect(page.locator("[data-map-app]")).to_have_attribute("data-point-longitude", "10.8")
    page.wait_for_function("() => !window.MicometeoMap.map.isMoving()")
    centre = page.evaluate(
        """() => {
          const point = window.MicometeoMap.map.getCenter();
          return {latitude: point.lat, longitude: point.lng};
        }"""
    )
    assert isclose(centre["latitude"], saved["latitude"], abs_tol=0.05)
    assert isclose(centre["longitude"], saved["longitude"], abs_tol=0.05)


def test_favorites_outside_point_shows_unavailable_state_without_area_request(
    page: Page, base_url: str
) -> None:
    _open_map(page, base_url)
    requests: list[str] = []

    def resolve_outside(route: Route) -> None:
        requests.append(route.request.url + (route.request.post_data or ""))
        route.fulfill(
            status=422,
            content_type="application/json",
            body=json.dumps({"code": "outside_configured_coverage"}),
        )

    def outside_squares(route: Route) -> None:
        requests.append(route.request.url + (route.request.post_data or ""))
        route.fulfill(
            status=400,
            content_type="application/json",
            body=json.dumps({"code": "outside_coverage"}),
        )

    page.route("**/api/v1/places/resolve**", resolve_outside)
    page.route("**/api/v1/squares**", outside_squares)
    page.evaluate(
        """key => window.localStorage.setItem(key, JSON.stringify({
          version: 1,
          items: [{
            id: 'outside', kind: 'point', latitude: 52, longitude: 13,
            name: 'Outside point'
          }]
        }))""",
        STORAGE_KEY,
    )
    _open_favorites(page)
    page.locator("[data-favorite-open]").click()
    page.wait_for_function(
        "() => document.querySelector('[data-map-app]').dataset.selectionSource === 'point'"
    )
    expect(page.locator("#mapmsgs")).to_contain_text("outside")
    expect(page.locator("aside[data-live-details]")).to_have_count(0)
    assert any("places/resolve" in request for request in requests)
    assert all("/api/v1/areas/" not in request for request in requests)
