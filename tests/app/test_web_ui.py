from __future__ import annotations

from datetime import date

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from web_ui.formatting import format_date, format_measurement


FIXTURE_STATES = (
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


def test_anonymous_visitor_reaches_landing_and_map() -> None:
    client = Client()

    landing = client.get(path=reverse(viewname="landing"))
    map_response = client.get(path=reverse(viewname="map"))

    assert landing.status_code == 200
    assert 'href="/map/"' in landing.content.decode()
    assert map_response.status_code == 200
    assert 'data-map-app' in map_response.content.decode()


def test_italian_landing_restores_sample_and_translates_percentage_copy() -> None:
    response = Client(HTTP_ACCEPT_LANGUAGE="it-IT,it;q=0.9").get(path="/")
    body = response.content.decode()

    assert response.status_code == 200
    assert "1.388 m s.l.m." in body
    assert "Scala di Probabilità Micometeo" in body
    assert body.count("data-probability-card") == 4
    assert "Sfuggente / Secco" in body
    assert "Condizioni Basali" in body
    assert "Altamente Propizio" in body
    assert "Almeno 10% di bosco" in body
    assert "I quadrati con meno del 10% di bosco non ricevono una stima." in body
    assert "The forest map says" not in body
    assert "At least 10% forest" not in body
    assert "%%" not in body
    assert '<svg class="language-icon" width="20" height="20"' in body


def test_english_landing_keeps_translated_sample_and_probability_scale() -> None:
    response = Client(HTTP_ACCEPT_LANGUAGE="en-GB,en;q=0.9").get(path="/")
    body = response.content.decode()

    assert response.status_code == 200
    assert "1,388 m above sea level" in body
    assert "Micometeo probability scale" in body
    assert body.count("data-probability-card") == 4
    assert "At least 10% forest" in body
    assert "%%" not in body


def test_italian_landing_names_tuscany_and_other_regions_coming_soon() -> None:
    response = Client(HTTP_ACCEPT_LANGUAGE="it-IT,it;q=0.9").get(path="/")
    body = response.content.decode()

    assert response.status_code == 200
    assert "Toscana" in body
    assert "Altre regioni in arrivo" in body
    assert "Altre regioni arriveranno presto" in body
    for text in ("tutta Italia", "tutta l'Italia", "Sicilia", "Sardegna"):
        assert text not in body


def test_english_landing_names_tuscany_and_other_regions_coming_soon() -> None:
    response = Client(HTTP_ACCEPT_LANGUAGE="en-GB,en;q=0.9").get(path="/")
    body = response.content.decode()

    assert response.status_code == 200
    assert "Tuscany" in body
    assert "Other regions coming soon" in body
    assert "Other regions are coming soon" in body
    for text in ("all Italy", "Sicily", "Sardinia"):
        assert text not in body


@override_settings(MICOMETEO_UI_FIXTURE_PAGES=True)
@pytest.mark.parametrize("state", FIXTURE_STATES)
def test_fixture_route_exposes_one_visible_named_state(state: str) -> None:
    response = Client().get(
        path=reverse(viewname="map-fixture", kwargs={"fixture": state})
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert f'data-fixture="{state}"' in body
    assert body.count('data-state-message') == 1


@override_settings(MICOMETEO_UI_FIXTURE_PAGES=False)
def test_fixture_route_is_off_by_default_and_production_map_has_no_fixture_data() -> None:
    client = Client()

    fixture_response = client.get(
        path=reverse(viewname="map-fixture", kwargs={"fixture": "loading"})
    )
    production_body = client.get(path=reverse(viewname="map")).content.decode()

    assert fixture_response.status_code == 404
    assert 'data-fixture="ready"' not in production_body
    assert "abetone-illustrative" not in production_body
    assert ">42%<" not in production_body


@override_settings(MICOMETEO_UI_FIXTURE_PAGES=True)
def test_map_root_exposes_persistent_state_contract() -> None:
    query = (
        "?square=abetone&date=2026-10-11&assessment=2026-10-10"
        "&update=update-20261011&center=44.133,10.664&zoom=13"
    )
    response = Client().get(
        path=f'{reverse(viewname="map-fixture", kwargs={"fixture": "ready"})}{query}',
        **{"HTTP_ACCEPT_LANGUAGE": "it-IT,it;q=0.9"},
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert 'data-language="it"' in body
    assert 'data-selected-square="abetone"' in body
    assert 'data-target-date="2026-10-11"' in body
    assert 'data-assessment-date="2026-10-10"' in body
    assert 'data-update-id="update-20261011"' in body
    assert 'data-map-center="44.133,10.664"' in body
    assert 'data-map-zoom="13"' in body
    assert 'data-details-open="true"' in body


@override_settings(MICOMETEO_UI_FIXTURE_PAGES=True)
def test_ready_fixture_uses_approved_assessment_window_and_selected_date() -> None:
    response = Client().get(
        path=reverse(viewname="map-fixture", kwargs={"fixture": "ready"})
        + "?square=abetone-illustrative&assessment=2026-10-12"
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert 'data-target-date="2026-10-15"' in body
    assert 'data-assessment-date="2026-10-12"' in body
    assert body.count('class="date-btn') == 8
    assert 'data-date="2026-10-15"' in body
    assert 'data-intl-date="2026-10-15" aria-pressed="true"' in body
    assert "48%" in body
    assert "15 October 2026" in body


@override_settings(MICOMETEO_UI_FIXTURE_PAGES=True)
def test_ready_fixture_opens_default_illustrative_details() -> None:
    response = Client().get(
        path=reverse(viewname="map-fixture", kwargs={"fixture": "ready"})
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert 'data-selected-square="abetone-illustrative"' in body
    assert 'data-details-open="true"' in body
    assert '<aside class="details"' in body


@pytest.mark.parametrize("state", ["older_update", "request_error"])
@override_settings(MICOMETEO_UI_FIXTURE_PAGES=True)
def test_retained_fixture_preserves_last_forecast_date_without_assessment(
    state: str,
) -> None:
    path = (
        f'{reverse(viewname="map-fixture", kwargs={"fixture": state})}'
        "?date=2026-10-19"
    )
    client = Client()

    for _ in range(2):
        response = client.get(path=path)
        body = response.content.decode()

        assert response.status_code == 200
        assert 'data-target-date="2026-10-19"' in body
        assert 'data-assessment-date="2026-10-11"' in body
        assert 'data-date="2026-10-19"' in body
        assert 'data-intl-date="2026-10-19" aria-pressed="true"' in body
        assert "38%" in body


@pytest.mark.parametrize("assessment", ["9999-12-31", "0001-01-01"])
@override_settings(MICOMETEO_UI_FIXTURE_PAGES=True)
def test_retained_fixture_rejects_unsupported_extreme_assessment_date(
    assessment: str,
) -> None:
    response = Client().get(
        path=(
            f'{reverse(viewname="map-fixture", kwargs={"fixture": "older_update"})}'
            f"?assessment={assessment}&date={assessment}"
        )
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert 'data-assessment-date="2026-10-11"' in body
    assert 'data-target-date="2026-10-12"' in body


def test_language_cookie_overrides_browser_language_without_cookie_on_fallback() -> None:
    fallback_client = Client(HTTP_ACCEPT_LANGUAGE="it-IT,it;q=0.9")
    fallback = fallback_client.get(path=reverse(viewname="map"))
    assert 'lang="it"' in fallback.content.decode()
    assert "micometeo_language" not in fallback.cookies

    selected_client = Client(HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9")
    selected_client.cookies["micometeo_language"] = "it"
    selected = selected_client.get(path=reverse(viewname="map"))
    assert 'lang="it"' in selected.content.decode()


@pytest.mark.parametrize(
    ("accept_language", "expected_language"),
    [("it-IT,it;q=0.9", "it"), ("en-GB,en;q=0.9", "en"), ("fr-FR,fr;q=0.9", "en")],
)
def test_supported_and_unsupported_browser_languages_have_safe_fallback(
    accept_language: str, expected_language: str
) -> None:
    response = Client(HTTP_ACCEPT_LANGUAGE=accept_language).get(
        path=reverse(viewname="map")
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert f'lang="{expected_language}"' in body


def test_formatting_keeps_calendar_day_and_localizes_number() -> None:
    selected = date(year=2026, month=10, day=11)

    assert format_date(selected, language="it") == "11 ottobre 2026"
    assert format_date(selected, language="en") == "11 October 2026"
    assert format_measurement(12.5, unit="mm", language="it") == "12,5 mm"
    assert format_measurement(12.5, unit="mm", language="en") == "12.5 mm"


@pytest.mark.django_db
def test_api_response_keeps_fixed_language_headers() -> None:
    response = Client(HTTP_ACCEPT_LANGUAGE="it-IT,it;q=0.9").get(
        path="/api/v1/health"
    )

    assert response.status_code in {200, 503}
    assert "Accept-Language" not in response.get("Vary", "")
    assert "Content-Language" not in response
