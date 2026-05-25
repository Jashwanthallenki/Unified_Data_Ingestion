"""Ingestion API endpoints."""
from __future__ import annotations

import csv
import io
import json
from datetime import date

from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView

from .adapters import sap as sap_adapter
from .adapters import travel as travel_adapter
from .adapters import utility as utility_adapter
from .models import IngestionBatch, RawRecord
from .serializers import (
    ExclusionRowSerializer,
    IngestionBatchSerializer,
    RawRecordSerializer,
)
from .services.lookup_context import LookupContext
from .services.orchestrator import persist_batch
from .services.tenant_resolver import get_tenant


def _read_uploaded_csv(uploaded_file) -> list[dict]:
    raw = uploaded_file.read()
    if isinstance(raw, bytes):
        # Strip UTF-8 BOM if present
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        text = raw.decode("utf-8", errors="replace")
    else:
        text = raw
    # Sniff delimiter (comma or semicolon)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return list(reader)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


class SapUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "Missing file field 'file'."}, status=status.HTTP_400_BAD_REQUEST)
        kind = (request.data.get("kind") or "mb51").strip().lower()
        if kind not in {"mb51", "me2m"}:
            return Response({"detail": f"Unknown kind '{kind}'. Use mb51 or me2m."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            rows = _read_uploaded_csv(upload)
        except Exception as exc:  # pragma: no cover — defensive
            return Response({"detail": f"Failed to parse CSV: {exc}"},
                            status=status.HTTP_400_BAD_REQUEST)

        tenant = get_tenant()
        ctx = LookupContext.load(tenant)
        if kind == "mb51":
            adapter_result = sap_adapter.adapt_mb51(rows, ctx)
        else:
            adapter_result = sap_adapter.adapt_me2m(rows, ctx)

        batch = persist_batch(
            tenant=tenant,
            source_type="sap",
            ingestion_method="FILE_UPLOAD",
            original_filename=upload.name,
            api_sync_range_start=None,
            api_sync_range_end=None,
            adapter_result=adapter_result,
            ctx=ctx,
            notes=f"SAP {kind.upper()} upload; header={adapter_result.metadata.get('header_language')}",
        )
        return Response(IngestionBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class UtilityUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "Missing file field 'file'."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            rows = _read_uploaded_csv(upload)
        except Exception as exc:
            return Response({"detail": f"Failed to parse CSV: {exc}"},
                            status=status.HTTP_400_BAD_REQUEST)

        tenant = get_tenant()
        ctx = LookupContext.load(tenant)
        adapter_result = utility_adapter.adapt_utility(rows, ctx)
        batch = persist_batch(
            tenant=tenant,
            source_type="utility",
            ingestion_method="FILE_UPLOAD",
            original_filename=upload.name,
            api_sync_range_start=None,
            api_sync_range_end=None,
            adapter_result=adapter_result,
            ctx=ctx,
            notes="Utility electricity upload",
        )
        return Response(IngestionBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class TravelSyncView(APIView):
    parser_classes = [JSONParser, FormParser]

    def post(self, request, *args, **kwargs):
        start = _parse_date(request.data.get("start_date"))
        end = _parse_date(request.data.get("end_date"))

        # Call the mock travel sync endpoint internally (no HTTP hop).
        from mock_travel.views import _load_fixture, _trip_overlaps

        fixture = _load_fixture()
        if start or end:
            trips = [t for t in fixture.get("trips", []) if _trip_overlaps(t, start, end)]
        else:
            trips = list(fixture.get("trips", []))

        tenant = get_tenant()
        ctx = LookupContext.load(tenant)
        adapter_result = travel_adapter.adapt_travel(trips, ctx)
        batch = persist_batch(
            tenant=tenant,
            source_type="travel",
            ingestion_method="API_PULL",
            original_filename=None,
            api_sync_range_start=start,
            api_sync_range_end=end,
            adapter_result=adapter_result,
            ctx=ctx,
            notes=f"Travel sync {start} → {end}; {len(trips)} trips ingested",
        )
        return Response(IngestionBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class BatchListView(ListAPIView):
    serializer_class = IngestionBatchSerializer

    def get_queryset(self):
        tenant = get_tenant()
        qs = IngestionBatch.objects.filter(tenant=tenant).order_by("-uploaded_at")
        source = self.request.query_params.get("source")
        if source:
            qs = qs.filter(source_type=source.lower())
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter.upper())
        return qs


class BatchDetailView(RetrieveAPIView):
    serializer_class = IngestionBatchSerializer
    lookup_url_kwarg = "batch_id"

    def get_object(self):
        tenant = get_tenant()
        return get_object_or_404(
            IngestionBatch, tenant=tenant, id=self.kwargs["batch_id"]
        )


class BatchRawRecordsView(ListAPIView):
    serializer_class = RawRecordSerializer

    def get_queryset(self):
        tenant = get_tenant()
        return RawRecord.objects.filter(
            tenant=tenant, batch_id=self.kwargs["batch_id"]
        ).order_by("row_number")


class BatchExclusionsView(ListAPIView):
    serializer_class = ExclusionRowSerializer

    def get_queryset(self):
        tenant = get_tenant()
        return RawRecord.objects.filter(
            tenant=tenant, batch_id=self.kwargs["batch_id"],
        ).exclude(exclusion_reason__isnull=True).exclude(exclusion_reason="").order_by("row_number")
