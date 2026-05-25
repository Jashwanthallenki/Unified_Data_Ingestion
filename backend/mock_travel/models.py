"""Storage for trips uploaded to the mock travel platform.

The mock travel API normally serves bundled fixture data
(`fixtures/travel/mock_response.json`). Uploads land here and the
sync endpoint returns `fixture_trips + UploadedTravelTrip rows`.
Not tenant-scoped — the mock simulates an external system that
doesn't know about our tenant model.
"""
from __future__ import annotations

import uuid

from django.db import models


class UploadedTravelTrip(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trip_payload = models.JSONField()
    source_label = models.CharField(max_length=128, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "uploaded_travel_trip"
        ordering = ["-uploaded_at"]
        indexes = [models.Index(fields=["-uploaded_at"])]

    def __str__(self) -> str:
        trip_id = (self.trip_payload or {}).get("trip_id", "?")
        return f"UploadedTravelTrip {trip_id} ({self.uploaded_at:%Y-%m-%d})"
