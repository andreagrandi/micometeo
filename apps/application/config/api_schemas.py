"""Shared error fields for the versioned application API."""

from typing import Any

from ninja import Schema


class ApiErrorSchema(Schema):
    """Describe one request error with a stable translation key."""

    code: str
    message: str
    message_key: str
    details: dict[str, Any] | None = None
