"""Mock Concur/Navan-style travel sync endpoint.

GET  /api/mock-travel/sync/        — returns bundled fixture + previously uploaded trips,
                                     filtered by start_date/end_date.
POST /api/mock-travel/upload/      — accepts a JSON file (multipart) OR a JSON body in
                                     Concur/Navan shape ({trips: [...]}); appends trips
                                     to the upload pool. Trips persist across syncs.
GET  /api/mock-travel/uploads/     — list/inspect what's been uploaded (debug aid).
DELETE /api/mock-travel/uploads/   — clear the upload pool (does not touch the fixture).
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UploadedTravelTrip


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _trip_overlaps(trip: dict, start: date | None, end: date | None) -> bool:
    """A trip overlaps the requested range if [start_date, end_date] intersects [start, end]."""
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


def _uploaded_trips() -> list[dict]:
    """Read uploaded trips from DB — newest first (consistent with model ordering)."""
    return [row.trip_payload for row in UploadedTravelTrip.objects.all()]


def get_all_trips() -> list[dict]:
    """Public helper used by both the mock sync endpoint and the ingestion adapter trigger."""
    return list(_load_fixture().get("trips", [])) + _uploaded_trips()


# -------- Sync (read) --------

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
        all_trips = get_all_trips()
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
                "fixture_trip_count": len(fixture.get("trips", [])),
                "uploaded_trip_count": UploadedTravelTrip.objects.count(),
                "start_date": start.isoformat() if start else None,
                "end_date": end.isoformat() if end else None,
                "trips": page_trips,
            },
            status=status.HTTP_200_OK,
        )


# -------- Upload (write) --------

class TravelUploadView(APIView):
    """POST /api/mock-travel/upload/

    Accepts EITHER:
      - multipart/form-data with field `file` (a .json file in Concur/Navan shape), or
      - application/json body in Concur/Navan shape: {"trips": [...]}.

    Optional form field / JSON key `source_label` is stored on each uploaded trip
    for debugging ("Concur Q1 export.json", "Navan March pull", etc.).

    Trips are appended to the upload pool. The next `/api/mock-travel/sync/` (and
    the next sync-button click in the UI) will see them.
    """

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, *args, **kwargs):
        upload = request.FILES.get("file")
        source_label = (request.data.get("source_label") or "").strip()

        if upload is not None:
            try:
                raw = upload.read()
                if isinstance(raw, bytes):
                    if raw.startswith(b"\xef\xbb\xbf"):
                        raw = raw[3:]
                    text = raw.decode("utf-8", errors="replace")
                else:
                    text = raw
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                return Response(
                    {"detail": f"Uploaded file is not valid JSON: {exc.msg} (line {exc.lineno}, col {exc.colno})"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not source_label:
                source_label = getattr(upload, "name", "") or ""
        else:
            payload = request.data
            if not isinstance(payload, dict):
                return Response(
                    {"detail": "JSON body must be an object with a 'trips' array."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Accept either {"trips": [...]} (Concur/Navan shape) or a bare list of trips.
        if isinstance(payload, list):
            trips = payload
        elif isinstance(payload, dict):
            trips = payload.get("trips")
        else:
            trips = None

        if not isinstance(trips, list):
            return Response(
                {"detail": "Payload must contain a 'trips' array (or be a bare array of trip objects)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build the set of trip_ids that already exist — across both the bundled
        # fixture and previously uploaded trips. Re-uploading the same file (or
        # a file overlapping a prior upload) must not create phantom duplicates.
        existing_trip_ids: set[str] = set()
        for fixture_trip in _load_fixture().get("trips", []):
            tid = fixture_trip.get("trip_id")
            if tid:
                existing_trip_ids.add(tid)
        for payload in UploadedTravelTrip.objects.values_list("trip_payload", flat=True):
            tid = (payload or {}).get("trip_id")
            if tid:
                existing_trip_ids.add(tid)

        # Shape validation + dedup. Tracks trip_ids seen *within this request*
        # too, so an upload containing trip_id "X" twice keeps only the first.
        rejected: list[dict] = []
        accepted: list[dict] = []
        seen_in_request: set[str] = set()
        for idx, trip in enumerate(trips):
            if not isinstance(trip, dict):
                rejected.append({"index": idx, "reason": "trip is not an object"})
                continue
            if "trip_id" not in trip and "segments" not in trip:
                rejected.append({"index": idx, "reason": "missing both trip_id and segments"})
                continue
            trip_id = trip.get("trip_id")
            if trip_id:
                if trip_id in existing_trip_ids:
                    rejected.append({
                        "index": idx,
                        "trip_id": trip_id,
                        "reason": "trip_id already in pool (fixture or prior upload)",
                    })
                    continue
                if trip_id in seen_in_request:
                    rejected.append({
                        "index": idx,
                        "trip_id": trip_id,
                        "reason": "duplicate trip_id within this upload",
                    })
                    continue
                seen_in_request.add(trip_id)
            accepted.append(trip)

        UploadedTravelTrip.objects.bulk_create(
            [UploadedTravelTrip(trip_payload=t, source_label=source_label) for t in accepted]
        )

        return Response(
            {
                "accepted_count": len(accepted),
                "rejected_count": len(rejected),
                "rejected": rejected[:20],  # cap so the response stays small
                "total_uploaded_count": UploadedTravelTrip.objects.count(),
                "source_label": source_label,
            },
            status=status.HTTP_201_CREATED,
        )


class TravelUploadInspectView(APIView):
    """GET /api/mock-travel/uploads/  — list what's in the pool (latest first, capped at 100).
    DELETE /api/mock-travel/uploads/  — clear the upload pool (fixture trips remain)."""

    def get(self, request, *args, **kwargs):
        qs = UploadedTravelTrip.objects.all()[:100]
        return Response(
            {
                "total_uploaded_count": UploadedTravelTrip.objects.count(),
                "returned_count": len(qs),
                "trips": [
                    {
                        "id": str(row.id),
                        "uploaded_at": row.uploaded_at.isoformat(),
                        "source_label": row.source_label,
                        "trip_id": (row.trip_payload or {}).get("trip_id"),
                        "trip": row.trip_payload,
                    }
                    for row in qs
                ],
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, *args, **kwargs):
        deleted, _ = UploadedTravelTrip.objects.all().delete()
        return Response({"deleted_count": deleted}, status=status.HTTP_200_OK)
