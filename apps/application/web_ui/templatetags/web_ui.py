from django import template

from web_ui.formatting import format_date, format_measurement, format_short_date


register = template.Library()


@register.filter
def ui_date(value, language: str) -> str:
    return format_date(value, language=language)


@register.filter
def ui_short_date(value, language: str) -> str:
    return format_short_date(value, language=language)


@register.simple_tag
def ui_measurement(value, unit: str, language: str) -> str:
    return format_measurement(value, unit=unit, language=language)
