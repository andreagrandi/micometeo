from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import formats, timezone, translation

from .formatting import format_date, format_measurement, format_short_date, format_weekday
from .landing_examples import landing_examples
from .translations import labels_for


FIXTURE_STATES = {
    "ready": "ready",
    "loading": "loading",
    "first_fetch": "first_fetch",
    "missing_data": "missing_data",
    "older_update": "older_update",
    "request_error": "request_error",
    "no_results": "no_results",
    "location_denied": "location_denied",
    "storage_unavailable": "storage_unavailable",
    "less_forest": "less_forest",
}

FIXTURE_STATES_WITH_SQUARE = {
    "loading",
    "first_fetch",
    "missing_data",
    "older_update",
    "request_error",
    "less_forest",
    "storage_unavailable",
}

FIXTURE_DATE_COUNT = 8
FIXTURE_ASSESSMENT = date(year=2026, month=10, day=12)
RETAINED_ASSESSMENT = date(year=2026, month=10, day=11)


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _supports_forecast_window(value: date, *, days: int = FIXTURE_DATE_COUNT) -> bool:
    return date.min < value <= date.max - timedelta(days=days - 1)


def _language(request: HttpRequest) -> str:
    return getattr(request, "LANGUAGE_CODE", "en")[:2]


def _dates(*, selected: date, language: str) -> list[dict[str, str]]:
    labels = labels_for(language)
    return [
        {
            "iso": (selected + timedelta(days=offset)).isoformat(),
            "label": labels["today"] if offset == 0 else format_date(selected + timedelta(days=offset), language=language),
            "short": format_short_date(selected + timedelta(days=offset), language=language),
            "weekday": labels["today"] if offset == 0 else format_weekday(selected + timedelta(days=offset), language=language),
        }
        for offset in range(8)
    ]


def _long_date(value: date, *, language: str) -> str:
    with translation.override(language):
        result = formats.date_format(value, "l j F Y", use_l10n=True)
    return result[:1].upper() + result[1:]


def _base_context(request: HttpRequest, *, fixture: bool = False) -> dict[str, object]:
    language = _language(request)
    labels = labels_for(language)
    assessment = FIXTURE_ASSESSMENT if fixture else timezone.localdate()
    requested_assessment = request.GET.get("assessment", "")
    parsed_assessment = _parse_date(requested_assessment)
    if fixture and parsed_assessment is not None and _supports_forecast_window(parsed_assessment):
        assessment = parsed_assessment
    selected = assessment + timedelta(days=3) if fixture else assessment
    parsed_selected = _parse_date(request.GET.get("date", ""))
    if parsed_selected is not None:
        selected = parsed_selected
    if not 0 <= (selected - assessment).days <= 7:
        selected = assessment
    return {
        "language": language,
        "labels": labels,
        "alternate_language": "it" if language == "en" else "en",
        "dates": _dates(selected=assessment, language=language),
        "selected_date": selected,
        "selected_date_display": format_date(selected, language=language),
        "assessment_date": assessment,
        "assessment_date_display": format_date(assessment, language=language),
        "target_date": selected.isoformat(),
        "date_selected_index": (selected - assessment).days,
        "sample_measurement": format_measurement(Decimal("12.5"), unit="mm", language=language),
    }


def _apply_fixture_dates(
    context: dict[str, object],
    request: HttpRequest,
    *,
    fixture: str,
) -> None:
    """Keep retained-result fixtures on the approved forecast dates."""
    if fixture not in {"older_update", "request_error"}:
        return
    requested_assessment = _parse_date(request.GET.get("assessment", ""))
    if requested_assessment is not None and _supports_forecast_window(
        requested_assessment, days=FIXTURE_DATE_COUNT + 1
    ):
        assessment = requested_assessment
    else:
        assessment = RETAINED_ASSESSMENT
    forecast_start = assessment + timedelta(days=1)
    requested_selected = _parse_date(request.GET.get("date", ""))
    default_selected = forecast_start + timedelta(days=3)
    if requested_selected is None:
        selected = default_selected
    elif forecast_start <= requested_selected <= forecast_start + timedelta(days=7):
        selected = requested_selected
    else:
        selected = forecast_start
    language = str(context["language"])
    context.update(
        {
            "dates": _dates(selected=forecast_start, language=language),
            "selected_date": selected,
            "selected_date_display": format_date(selected, language=language),
            "assessment_date": assessment,
            "assessment_date_display": format_date(assessment, language=language),
            "target_date": selected.isoformat(),
            "date_selected_index": (selected - forecast_start).days,
        }
    )


def landing(request: HttpRequest) -> HttpResponse:
    """Render the public landing page."""
    context = _base_context(request)
    context.update(landing_examples(language=str(context["language"])))
    return render(request, "web_ui/landing.html", context)


def map_page(request: HttpRequest, fixture: str | None = None) -> HttpResponse:
    """Render the persistent map shell and optional test fixture."""
    if fixture is not None and not getattr(settings, "SPORAMETEO_UI_FIXTURE_PAGES", False):
        raise Http404("UI fixture pages are disabled")
    if fixture is not None and fixture not in FIXTURE_STATES:
        raise Http404("Unknown UI fixture")
    context = _base_context(request, fixture=fixture is not None)
    if fixture is not None:
        _apply_fixture_dates(context, request, fixture=fixture)
    requested_square = request.GET.get("square", "")
    fixture_state = FIXTURE_STATES.get(fixture, "ready")
    selected_square = requested_square or (
        "abetone-illustrative"
        if fixture is not None
        and (fixture_state == "ready" or fixture_state in FIXTURE_STATES_WITH_SQUARE)
        else ""
    )
    details_open = bool(
        fixture is not None
        and (fixture_state == "ready" or fixture_state in FIXTURE_STATES_WITH_SQUARE)
        and selected_square
    )
    estimates = (42, 45, 47, 48, 46, 43, 40, 38)
    if fixture is not None and fixture_state not in {"first_fetch", "missing_data", "less_forest"}:
        for item, estimate in zip(context["dates"], estimates, strict=True):
            item["estimate"] = str(estimate)
    has_estimate = fixture is not None and fixture_state not in {"first_fetch", "missing_data", "less_forest"}
    labels = context["labels"]
    update_display = labels["update_value"].format(date=context["assessment_date_display"])
    older_text_display = labels["older_text"].format(
        target=context["selected_date_display"],
        assessment=context["assessment_date_display"],
        update=update_display,
    )
    loading_display = labels["loading_date"].format(date=context["selected_date_display"])
    rain_until = context["assessment_date"] - timedelta(days=1)
    rain_note_display = labels["rain_note"].format(
        until=format_date(rain_until, language=str(context["language"]))
    )
    older_percent_caption_display = labels["older_percent_caption"].format(
        date=_long_date(context["selected_date"], language=str(context["language"]))
    )
    if has_estimate:
        selected_estimate = str(estimates[context["date_selected_index"]])
    else:
        selected_estimate = ""
    forest_share = 6 if fixture_state == "less_forest" else 68
    facts_display = labels["facts_text"].format(forest=f"{forest_share}%")
    context.update(
        {
            "has_estimate": has_estimate,
            "selected_estimate": selected_estimate,
            "forest_share": forest_share,
            "facts_display": facts_display,
            "update_display": update_display,
            "older_text_display": older_text_display,
            "loading_display": loading_display,
            "rain_note_display": rain_note_display,
            "selected_date_full_display": _long_date(
                context["selected_date"], language=str(context["language"])
            ),
            "older_percent_caption_display": older_percent_caption_display,
            "stored_target_date_display": context["selected_date_display"],
            "stored_assessment_date_display": context["assessment_date_display"],
        }
    )
    context.update(
        {
            "fixture": fixture,
            "fixture_state": fixture_state,
            "selected_square": selected_square,
            "details_open": details_open,
            "update_id": request.GET.get("update", "illustrative-2026-10-12" if fixture == "ready" else ""),
            "result_id": request.GET.get("result", "illustrative-result-42" if fixture == "ready" else ""),
            "map_center": request.GET.get(
                "center",
                "44.133,10.664" if fixture is not None else "",
            ),
            "map_zoom": request.GET.get("zoom", "11"),
        }
    )
    return render(request, "web_ui/map.html", context)


def privacy(request: HttpRequest) -> HttpResponse:
    """Render the public privacy policy page."""
    language = _language(request)
    context = {"language": language, "labels": labels_for(language)}
    return render(request, "web_ui/privacy.html", context)
