from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.utils import formats, translation


def format_decimal(value: Decimal | float | int, *, language: str) -> str:
    """Format one decimal with the selected language separator."""
    with translation.override(language):
        return formats.number_format(Decimal(str(value)), decimal_pos=1, use_l10n=True)


def format_measurement(value: Decimal | float | int, *, unit: str, language: str) -> str:
    """Format a measurement with a localized decimal separator."""
    return f"{format_decimal(value, language=language)} {unit}"


def format_date(value: date, *, language: str) -> str:
    """Format a calendar day without changing its Europe/Rome date."""
    with translation.override(language):
        result = formats.date_format(value, "j F Y", use_l10n=True)
    return result.lower() if language == "it" else result


def format_short_date(value: date, *, language: str) -> str:
    """Format a short date for the date strip."""
    with translation.override(language):
        result = formats.date_format(value, "j M", use_l10n=True)
    return result.lower() if language == "it" else result


def format_weekday(value: date, *, language: str) -> str:
    """Format a short weekday for the date strip."""
    with translation.override(language):
        return formats.date_format(value, "D", use_l10n=True)
