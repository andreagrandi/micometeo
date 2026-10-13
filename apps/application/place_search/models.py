"""Persistent cache and request throttle records for place search."""

from django.db import models


class PlaceSearchCache(models.Model):
    """Cache one normalized provider query and its result list."""

    normalized_query = models.CharField(max_length=120)
    language = models.CharField(max_length=12, default="it")
    endpoint = models.URLField(max_length=500)
    results = models.JSONField(default=list)
    fetched_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["normalized_query", "language", "endpoint"],
                name="place_search_cache_query_language_endpoint_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["expires_at"], name="place_search_cache_expiry_idx"),
            models.Index(
                fields=["normalized_query", "language"],
                name="place_search_cache_lookup_idx",
            ),
        ]


class PlaceSearchThrottle(models.Model):
    """Store the last provider request for one database-locked throttle."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    last_request_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
