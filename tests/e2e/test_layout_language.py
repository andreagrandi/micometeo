from __future__ import annotations

import sys
from collections.abc import Mapping
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import Page, expect


STATE_FIXTURES = (
    "loading",
    "first_fetch",
    "missing_data",
    "older_update",
    "request_error",
    "no_results",
    "location_denied",
    "storage_unavailable",
    "less_forest",
)
PHONE_SIZES = ((390, 844), (320, 568))
STATE_QUERY = (
    "square=abetone&date=2026-10-11&assessment=2026-10-10"
    "&update=update-20261011&center=44.133,10.664&zoom=13"
)
CANONICAL_QUERY = "square=abetone-illustrative&assessment=2026-10-12"


def _open_page(page: Page, *, url: str, headers: Mapping[str, str] | None = None) -> None:
    page.set_default_timeout(10_000)
    if headers is not None:
        page.set_extra_http_headers(headers=dict(headers))
    page.goto(url=url, wait_until="domcontentloaded")


def _state_query(url: str) -> dict[str, list[str]]:
    query = parse_qs(urlparse(url).query, keep_blank_values=True)
    return {key: values for key, values in query.items() if key != "lang"}


def _assert_no_horizontal_overflow(page: Page) -> None:
    dimensions = page.evaluate(
        """
        () => {
          const width = document.documentElement.clientWidth;
          const message = document.querySelector('[data-state-message]');
          const nodes = message
            ? [message, ...message.querySelectorAll('*')]
                .filter((node) => node.getAttribute('aria-hidden') !== 'true')
            : [];
          return {
            pageWidth: document.documentElement.scrollWidth,
            viewportWidth: width,
            messageText: message?.innerText.trim() || '',
            messageOverflow: nodes.some((node) =>
              node.getBoundingClientRect().right > width + 1 ||
              node.getBoundingClientRect().left < -1
            ),
          };
        }
        """
    )
    assert dimensions["pageWidth"] <= dimensions["viewportWidth"]
    assert dimensions["messageText"]
    assert dimensions["messageOverflow"] is False


def _tab_until_focused(
    page: Page, selector: str, *, browser_name: str, max_tabs: int = 40
) -> None:
    target = page.locator(selector).first
    # macOS WebKit reserves Tab for text fields and uses Alt+Tab for controls.
    tab_key = "Alt+Tab" if browser_name == "webkit" and sys.platform == "darwin" else "Tab"
    for _ in range(max_tabs):
        if target.evaluate("(element) => element === document.activeElement"):
            return
        page.keyboard.press(tab_key)
    assert target.evaluate("(element) => element === document.activeElement")


@pytest.mark.parametrize(
    ("accept_language", "expected_language"),
    [
        ("it-IT,it;q=0.9", "it"),
        ("en-GB,en;q=0.9", "en"),
        ("fr-FR,fr;q=0.9", "en"),
    ],
)
def test_browser_language_fallback(
    page: Page, base_url: str, accept_language: str, expected_language: str
) -> None:
    _open_page(
        page,
        url=f"{base_url}/map/",
        headers={"Accept-Language": accept_language},
    )

    expect(page.locator("html")).to_have_attribute("lang", expected_language)
    expect(page.locator("[data-map-app]")).to_have_attribute(
        "data-language", expected_language
    )
    expect(page.locator("button[data-language='it']")).to_be_visible()
    expect(page.locator("button[data-language='en']")).to_be_visible()


def test_explicit_language_switch_preserves_state_after_reload(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _open_page(
        page,
        url=f"{base_url}/map/fixture/ready/?{STATE_QUERY}",
        headers={"Accept-Language": "it-IT,it;q=0.9"},
    )
    root = page.locator("[data-map-app]")

    expect(root).to_have_attribute("data-language", "it")
    expect(root).to_have_attribute("data-selected-square", "abetone")
    expect(root).to_have_attribute("data-target-date", "2026-10-11")
    expect(root).to_have_attribute("data-assessment-date", "2026-10-10")
    expect(root).to_have_attribute("data-update-id", "update-20261011")
    expect(root).to_have_attribute("data-map-center", "44.133,10.664")
    expect(root).to_have_attribute("data-map-zoom", "13")
    expect(page.locator("aside[data-details]")).to_contain_text("11 ottobre 2026")
    italian_selected = page.locator(".date-btn[aria-pressed='true']")
    expect(italian_selected).to_have_attribute("data-date", "2026-10-11")
    expect(italian_selected).to_contain_text("11 ott")

    before_query = _state_query(page.url)
    page.locator("button[data-language='en']").click()
    page.wait_for_load_state(state="domcontentloaded")
    expect(page.locator("html")).to_have_attribute("lang", "en")
    expect(root).to_have_attribute("data-language", "en")
    expect(page.locator("aside[data-details]")).to_contain_text("11 October 2026")
    english_selected = page.locator(".date-btn[aria-pressed='true']")
    expect(english_selected).to_have_attribute("data-date", "2026-10-11")
    expect(english_selected).to_contain_text("11 Oct")
    assert _state_query(page.url) == before_query

    page.reload(wait_until="domcontentloaded")
    expect(page.locator("[data-map-app]")).to_have_attribute("data-language", "en")
    assert _state_query(page.url) == before_query


def test_state_controls_persist_panels_layers_and_sheet_after_language_switch(
    page: Page, base_url: str
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _open_page(
        page,
        url=f"{base_url}/map/fixture/ready/?{STATE_QUERY}&details=true",
        headers={"Accept-Language": "it-IT,it;q=0.9"},
    )
    root = page.locator("[data-map-app]")
    details = page.locator("aside[data-details]").first
    expect(details).to_be_visible()

    page.keyboard.press("Escape")
    page.locator("button[data-open-panel='layers']").first.click()
    page.locator('label.choice:has(input[value="contrast"])').click()
    overlay = page.locator("[data-overlay]").first
    overlay_before = overlay.get_attribute("aria-checked")
    overlay.click()
    page.locator("[data-opacity]").first.evaluate(
        """(element) => {
          element.value = '45';
          element.dispatchEvent(new Event('input', {bubbles: true}));
        }"""
    )
    page.set_viewport_size({"width": 1440, "height": 900})
    fold = page.locator("[data-fold='layers']").first
    fold_before = fold.get_attribute("aria-expanded")
    fold.click()
    fold_after = fold.get_attribute("aria-expanded")
    assert fold_before != fold_after
    expect(page.locator('input[name="background"][value="contrast"]')).to_be_checked()
    expect(page.locator("[data-opacity]").first).to_have_value("45")
    if overlay_before is not None:
        expect(overlay).to_have_attribute(
            "aria-checked", str(overlay_before != "true").lower()
        )
    else:
        expect(overlay).not_to_be_checked()

    page.locator("button[data-language='en']").click()
    page.wait_for_load_state(state="domcontentloaded")
    expect(root).to_have_attribute("data-language", "en")
    expect(root).to_have_attribute("data-details-open", "false")
    expect(page.locator('input[name="background"][value="contrast"]')).to_be_checked()
    expect(page.locator("[data-opacity]").first).to_have_value("45")
    assert page.locator("[data-fold='layers']").first.get_attribute("aria-expanded") == fold_after
    assert _state_query(page.url)["panel"] == ["layers"]


def test_sheet_height_persists_after_reload(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _open_page(
        page,
        url=f"{base_url}/map/fixture/ready/?{STATE_QUERY}&details=true",
    )
    details = page.locator("aside[data-details]").first
    sheet_before = details.get_attribute("data-sheet-height")
    page.locator("[data-sheet-height]").last.click()
    sheet_after = details.get_attribute("data-sheet-height")

    assert sheet_before != sheet_after
    page.reload(wait_until="domcontentloaded")
    expect(page.locator("aside[data-details]").first).to_have_attribute(
        "data-sheet-height", sheet_after
    )


@pytest.mark.parametrize("fixture", STATE_FIXTURES)
@pytest.mark.parametrize("viewport", PHONE_SIZES)
@pytest.mark.parametrize(
    ("accept_language", "expected_language"),
    [
        ("it-IT,it;q=0.9", "it"),
        ("en-GB,en;q=0.9", "en"),
    ],
)
def test_all_fixture_states_fit_supported_phone_widths(
    page: Page,
    base_url: str,
    fixture: str,
    viewport: tuple[int, int],
    accept_language: str,
    expected_language: str,
) -> None:
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    _open_page(
        page,
        url=f"{base_url}/map/fixture/{fixture}/",
        headers={"Accept-Language": accept_language},
    )

    expect(page.locator("html")).to_have_attribute("lang", expected_language)
    expect(page.locator("[data-map-app]")).to_have_attribute("data-fixture", fixture)
    expect(page.locator("[data-map-app]")).to_have_attribute(
        "data-language", expected_language
    )
    expect(page.locator("[data-state-message]")).to_be_visible()
    _assert_no_horizontal_overflow(page)


def test_keyboard_actions_restore_focus_and_close_details(
    page: Page, base_url: str, browser_name: str
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _open_page(
        page,
        url=f"{base_url}/map/fixture/ready/?{STATE_QUERY}",
    )

    _tab_until_focused(page, "#search-input", browser_name=browser_name)
    _tab_until_focused(page, "button[data-location]", browser_name=browser_name)
    _tab_until_focused(page, "button[data-favourites]", browser_name=browser_name)
    _tab_until_focused(page, ".date-btn", browser_name=browser_name)
    opener = page.locator("button[data-open-panel='layers']").first
    _tab_until_focused(
        page, "button[data-open-panel='layers']", browser_name=browser_name
    )
    page.keyboard.press("Enter")
    expect(opener).to_have_attribute("aria-expanded", "true")
    expect(page.locator("#layers-panel")).to_be_visible()
    overlay = page.locator("[data-overlay]").first
    overlay_before = overlay.get_attribute("aria-checked")
    _tab_until_focused(page, "[data-overlay]", browser_name=browser_name)
    page.keyboard.press("Enter")
    expect(overlay).to_have_attribute(
        "aria-checked", str(overlay_before != "true").lower()
    )
    page.keyboard.press("Escape")
    expect(opener).to_have_attribute("aria-expanded", "false")
    expect(opener).to_be_focused()

    page.goto(
        url=f"{base_url}/map/fixture/ready/?{STATE_QUERY}&details=true",
        wait_until="domcontentloaded",
    )
    expect(page.locator("[data-map-app]")).to_have_attribute("data-details-open", "true")
    page.keyboard.press("Escape")
    expect(page.locator("[data-map-app]")).to_have_attribute("data-details-open", "false")
    expect(page.locator("#map")).to_be_focused()


def test_canonical_fixture_renders_approved_dates_and_selected_estimate(
    page: Page, base_url: str
) -> None:
    _open_page(page, url=f"{base_url}/map/fixture/ready/?{CANONICAL_QUERY}")

    root = page.locator("[data-map-app]")
    expect(root).to_have_attribute("data-assessment-date", "2026-10-12")
    expect(root).to_have_attribute("data-target-date", "2026-10-15")
    expect(page.locator(".dates .date-btn")).to_have_count(8)
    selected = page.locator(".date-btn[aria-pressed='true']")
    expect(selected).to_have_attribute("data-date", "2026-10-15")
    expect(selected).to_contain_text("48%")
    expect(page.locator("aside[data-details]")).to_contain_text("15 October 2026")
    expect(page.locator(".date-assess")).to_contain_text("12 October 2026")

    page.locator(".date-btn[data-date='2026-10-17']").click()
    expect(root).to_have_attribute("data-target-date", "2026-10-17")
    expect(page.locator(".dates .date-btn")).to_have_count(8)
    selected = page.locator(".date-btn[aria-pressed='true']")
    expect(selected).to_have_attribute("data-date", "2026-10-17")
    expect(selected).to_contain_text("43%")
    expect(page.locator("aside[data-details]")).to_contain_text("17 October 2026")

    page.locator("button[data-language='it']").click()
    page.wait_for_load_state(state="domcontentloaded")
    expect(root).to_have_attribute("data-language", "it")
    expect(page.locator(".dates .date-btn")).to_have_count(8)
    expect(page.locator(".date-btn").first).to_have_attribute("data-date", "2026-10-12")
    expect(page.locator(".date-btn").last).to_have_attribute("data-date", "2026-10-19")
    selected = page.locator(".date-btn[aria-pressed='true']")
    expect(selected).to_have_attribute("data-date", "2026-10-17")
    expect(selected).to_contain_text("17 ott")
    expect(page.locator("aside[data-details]")).to_contain_text("17 ottobre 2026")

    page.reload(wait_until="domcontentloaded")
    expect(page.locator("[data-map-app]")).to_have_attribute(
        "data-target-date", "2026-10-17"
    )
    expect(page.locator(".date-btn[aria-pressed='true']")).to_have_attribute(
        "data-date", "2026-10-17"
    )
    expect(page.locator("aside[data-details]")).to_contain_text("17 ottobre 2026")


def test_browser_formatting_helpers_keep_calendar_day_and_units(
    page: Page, base_url: str
) -> None:
    _open_page(page, url=f"{base_url}/map/fixture/ready/?date=2026-10-11")
    english_values = page.evaluate(
        """
        () => {
          const formatting = window.MicometeoFormatting;
          return {
            date: formatting.formatDate('2026-10-11'),
            measurement: formatting.formatMeasurement(12.5, 'mm'),
          };
        }
        """
    )
    page.locator("button[data-language='it']").click()
    page.wait_for_load_state(state="domcontentloaded")
    italian_values = page.evaluate(
        """
        () => {
          const formatting = window.MicometeoFormatting;
          return {
            date: formatting.formatDate('2026-10-11'),
            measurement: formatting.formatMeasurement(12.5, 'mm'),
          };
        }
        """
    )

    assert english_values == {"date": "11 October 2026", "measurement": "12.5 mm"}
    assert italian_values == {"date": "11 ottobre 2026", "measurement": "12,5 mm"}


def test_normal_map_uses_neutral_center_without_fixture(
    page: Page, base_url: str
) -> None:
    _open_page(page, url=f"{base_url}/map/")

    root = page.locator("[data-map-app]")
    expect(root).to_have_attribute("data-map-center", "")
    expect(root).to_have_attribute("data-selected-square", "")


def test_invalid_fixture_dates_use_server_normalized_state(
    page: Page, base_url: str
) -> None:
    _open_page(
        page,
        url=(
            f"{base_url}/map/fixture/ready/?date=not-a-date&assessment=not-a-date"
        ),
    )

    root = page.locator("[data-map-app]")
    expect(root).to_have_attribute("data-assessment-date", "2026-10-12")
    expect(root).to_have_attribute("data-target-date", "2026-10-15")
    assert "not-a-date" not in page.url


def test_out_of_window_fixture_date_uses_server_normalized_state(
    page: Page, base_url: str
) -> None:
    _open_page(
        page,
        url=f"{base_url}/map/fixture/ready/?date=2026-10-30&assessment=2026-10-12",
    )

    root = page.locator("[data-map-app]")
    expect(root).to_have_attribute("data-assessment-date", "2026-10-12")
    expect(root).to_have_attribute("data-target-date", "2026-10-12")
    assert "date=2026-10-30" not in page.url


def test_no_results_state_stays_inside_search_results(
    page: Page, base_url: str
) -> None:
    _open_page(page, url=f"{base_url}/map/fixture/no_results/")

    expect(page.locator("[data-search-results]")).to_be_visible()
    expect(page.locator("[data-search-results] [data-state-message]")).to_be_visible()
    expect(page.locator(".mapcell [data-state-message]")).to_have_count(0)


def test_location_and_detail_actions_use_all_matching_controls(
    page: Page, base_url: str
) -> None:
    _open_page(
        page,
        url=f"{base_url}/map/fixture/missing_data/",
        headers={"Accept-Language": "it-IT,it;q=0.9"},
    )

    expect(page.locator("[data-try-again]")).to_have_count(2)
    expect(page.locator("aside[data-details] [data-center-select]")).to_have_count(1)
    page.locator(".mapmsgs [data-try-again]").click()
    page.wait_for_load_state(state="domcontentloaded")
    expect(page.locator("[data-map-app]")).to_have_attribute(
        "data-fixture", "missing_data"
    )
    page.locator("aside[data-details] [data-try-again]").click()
    page.wait_for_load_state(state="domcontentloaded")
    page.locator("aside[data-details] [data-center-select]").click()
    expect(page.locator("[data-map-app]")).to_have_attribute("data-details-open", "false")
    expect(page.locator("#map")).to_be_focused()
    expect(page.locator("[data-toast]")).to_contain_text(
        "La mappa live arriverà in un aggiornamento successivo."
    )

    page.locator("[data-location]").click()
    expect(page.locator("[data-toast]")).to_contain_text(
        "La ricerca dei luoghi e la posizione arriveranno in un aggiornamento successivo."
    )
