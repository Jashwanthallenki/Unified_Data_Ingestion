"""Mock Concur/Navan-style travel sync endpoint.

Filters the bundled fixture by `start_date` and `end_date` query parameters,
paginates the result, and returns it. Matches the shape a real Concur/Navan API
would return, so the same Travel ingestion adapter consumes it without changes.
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _trip_overlaps(trip: dict, start: date | None, end: date | None) -> bool:
    """A trip overlaps the requested range if its [start_date, end_date] intersects [start, end]."""
    t_start = _parse_date(trip.get("start_date"))
    t_end = _parse_date(trip.get("end_date") or trip.get("start_date"))
    if not t_start:
        return False
    if start and t_end and t_end < start:
        return False
    if end and t_start > end:
        return False
    return True


@lru_cache(maxsize=1)
def _load_fixture() -> dict:
    path: Path = settings.BASE_DIR / "fixtures" / "travel" / "mock_response.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


class TravelSyncView(APIView):
    """GET /api/mock-travel/sync/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&page=1&page_size=50"""

    def get(self, request, *args, **kwargs):
        start = _parse_date(request.query_params.get("start_date"))
        end = _parse_date(request.query_params.get("end_date"))
        try:
            page = max(1, int(request.query_params.get("page", "1")))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = min(200, max(1, int(request.query_params.get("page_size", "50"))))
        except (TypeError, ValueError):
            page_size = 50

        fixture = _load_fixture()
        all_trips = fixture.get("trips", [])
        if start or end:
            trips = [t for t in all_trips if _trip_overlaps(t, start, end)]
        else:
            trips = list(all_trips)

        total = len(trips)
        offset = (page - 1) * page_size
        page_trips = trips[offset:offset + page_size]

        return Response(
            {
                "provider": fixture.get("provider", "MockCorpTravel"),
                "schema_version": fixture.get("schema_version", "1.0"),
                "page": page,
                "page_size": page_size,
                "total_count": total,
                "returned_count": len(page_trips),
                "start_date": start.isoformat() if start else None,
                "end_date": end.isoformat() if end else None,
                "trips": page_trips,
            },
            status=status.HTTP_200_OK,
        )
