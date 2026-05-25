"""Persist an AdapterBatchResult into IngestionBatch + RawRecord + NormalizedActivity + ValidationIssue."""
from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from django.db import transaction
from django.utils import timezone

from activities.models import NormalizedActivity, ValidationIssue
from ingestion.models import IngestionBatch, RawRecord
from tenants.models import Tenant

from . import confidence as confidence_service
from .dedupe import build_activity_event_key, build_source_event_key, hash_payload
from .drafts import ActivityDraft, AdapterBatchResult
from .lookup_context import LookupContext
from .validation import severity_for


_ACTIVITY_FIELDS = [
    "source_type", "activity_type", "activity_subtype", "scope", "scope_category",
    "eligibility_status", "source_hierarchy_rank", "source_of_truth",
    "activity_basis", "calculation_method", "emission_method",
    "activity_date", "period_start", "period_end", "calendar_month", "billing_days",
    "facility_code", "facility_name", "facility_country",
    "origin", "destination",
    "quantity", "unit", "normalized_quantity", "normalized_unit", "usage_per_day",
    "currency", "amount",
    "vendor", "cost_center", "reference_id", "event_key", "parent_event_key",
    "is_duplicate", "duplicate_reason", "is_reversal", "reversal_of",
    "is_estimate", "estimate_reason", "requires_reconciliation",
    "emission_factor", "emission_factor_source", "co2e_kg",
    "data_quality_score", "confidence_level", "method_confidence",
    "flags", "field_provenance",
]


def _draft_to_kwargs(draft: ActivityDraft) -> dict[str, Any]:
    return {f: getattr(draft, f) for f in _ACTIVITY_FIELDS}


@transaction.atomic
def persist_batch(
    *,
    tenant: Tenant,
    source_type: str,
    ingestion_method: str,
    original_filename: str | None,
    api_sync_range_start: date | None,
    api_sync_range_end: date | None,
    adapter_result: AdapterBatchResult,
    ctx: LookupContext,
    file_hash: str | None = None,
    content_hash: str | None = None,
    sync_key: str | None = None,
    notes: str = "",
) -> IngestionBatch:
    """Create the batch and all child rows in one transaction."""
    duplicate_batch = _find_duplicate_batch(
        tenant=tenant,
        source_type=source_type,
        file_hash=file_hash,
        content_hash=content_hash,
        sync_key=sync_key,
    )
    batch_notes = notes
    if duplicate_batch is not None:
        warning = f"Possible duplicate of batch {duplicate_batch.id}"
        batch_notes = f"{notes}; {warning}" if notes else warning
    batch = IngestionBatch.objects.create(
        tenant=tenant,
        source_type=source_type,
        ingestion_method=ingestion_method,
        original_filename=original_filename,
        api_sync_range_start=api_sync_range_start,
        api_sync_range_end=api_sync_range_end,
        file_hash=file_hash,
        content_hash=content_hash,
        sync_key=sync_key,
        is_duplicate_file=duplicate_batch is not None,
        duplicate_of_batch=duplicate_batch,
        status="PROCESSING",
        notes=batch_notes,
        plant_lookup_version=ctx.plant_lookup_version,
        material_lookup_version=ctx.material_lookup_version,
        unit_mapping_version=ctx.unit_mapping_version,
        meter_mapping_version=ctx.meter_mapping_version,
        ef_version=ctx.ef_version,
    )

    parse_counter: Counter = Counter()
    elig_counter: Counter = Counter()
    activity_status_counter: Counter = Counter()
    confidence_counter: Counter = Counter()
    flagged = 0
    suspicious = 0
    llm_suggested = 0
    seen_rows: dict[str, RawRecord] = {}
    seen_events: dict[str, RawRecord] = {}

    for row_idx, row_result in enumerate(adapter_result.rows):
        raw_payload = _json_safe(row_result.raw_payload)
        row_hash = hash_payload(raw_payload)
        source_event_key = build_source_event_key(source_type, raw_payload)
        duplicate_raw = _find_duplicate_raw_record(
            tenant=tenant,
            batch=batch,
            source_type=source_type,
            row_hash=row_hash,
            source_event_key=source_event_key,
            seen_rows=seen_rows,
            seen_events=seen_events,
        )
        raw = RawRecord.objects.create(
            tenant=tenant,
            batch=batch,
            source_type=source_type,
            row_number=row_idx + 1,
            raw_payload=raw_payload,
            row_hash=row_hash,
            source_event_key=source_event_key or None,
            is_duplicate_row=duplicate_raw is not None,
            duplicate_of_raw_record=duplicate_raw,
            parse_status=row_result.parse_status,
            eligibility_status=row_result.eligibility_status,
            exclusion_reason=row_result.exclusion_reason,
            error_message=row_result.error_message,
        )
        if not duplicate_raw:
            seen_rows.setdefault(row_hash, raw)
            if source_event_key:
                seen_events.setdefault(source_event_key, raw)
        parse_counter[row_result.parse_status] += 1
        if row_result.eligibility_status:
            elig_counter[row_result.eligibility_status] += 1

        for draft in row_result.activities:
            _apply_duplicate_context(
                tenant=tenant,
                batch=batch,
                raw=raw,
                draft=draft,
                duplicate_batch=duplicate_batch,
                duplicate_raw=duplicate_raw,
                source_event_key=source_event_key,
            )
            kwargs = _draft_to_kwargs(draft)
            duplicate_activity = getattr(draft, "_duplicate_of_activity", None)
            # Decimal/date sanitation happens inside Django; nothing to do here.
            activity = NormalizedActivity.objects.create(
                tenant=tenant,
                batch=batch,
                raw_record=raw,
                duplicate_of_activity=duplicate_activity,
                **kwargs,
            )
            for issue in draft.issues:
                ValidationIssue.objects.create(
                    tenant=tenant,
                    activity=activity,
                    issue_code=issue.issue_code,
                    severity=issue.severity or severity_for(issue.issue_code),
                    message=issue.message,
                )
            activity_status_counter[activity.eligibility_status] += 1
            confidence_counter[activity.confidence_level] += 1
            if activity.flags:
                flagged += 1
            if any(f in {"SUSPICIOUS_HIGH_QUANTITY", "SUSPICIOUS_HIGH_VALUE", "USAGE_SPIKE_AFTER_DAY_NORMALIZATION"}
                   for f in activity.flags):
                suspicious += 1
            if "LLM_SUGGESTED_FIELD" in activity.flags or activity.llm_suggestions:
                llm_suggested += 1

    # Roll up counts onto the batch
    total = sum(parse_counter.values())
    batch.total_rows = total
    batch.raw_rows_stored = total
    batch.failed_rows = parse_counter.get("FAILED", 0)
    batch.excluded_rows = parse_counter.get("EXCLUDED", 0)
    batch.not_relevant_rows = elig_counter.get("NOT_RELEVANT", 0)
    batch.eligible_rows = activity_status_counter.get("ELIGIBLE", 0)
    batch.successful_rows = activity_status_counter.get("ELIGIBLE", 0)
    batch.flagged_rows = flagged
    batch.suspicious_rows = suspicious
    batch.low_confidence_rows = confidence_counter.get("LOW", 0) + confidence_counter.get("FAILED", 0)
    batch.llm_suggested_rows = llm_suggested
    batch.pending_rows = (
        activity_status_counter.get("ELIGIBLE", 0)
        + activity_status_counter.get("NEEDS_REVIEW", 0)
    )
    batch.approved_rows = 0
    batch.rejected_rows = 0
    batch.locked_rows = 0

    if parse_counter.get("FAILED", 0) and parse_counter.get("PARSED", 0) == 0:
        batch.status = "FAILED"
    elif parse_counter.get("FAILED", 0) > 0:
        batch.status = "PARTIAL"
    else:
        batch.status = "COMPLETE"

    batch.save()
    return batch


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    """Recursively coerce non-JSON-serializable types to JSON-safe ones."""
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, dict):
            out[k] = _json_safe(v)
        elif isinstance(v, list):
            out[k] = [_json_safe(i) if isinstance(i, dict) else (i if isinstance(i, (str, int, float, bool)) or i is None else str(i)) for i in v]
        else:
            out[k] = str(v)
    return out


def _find_duplicate_batch(
    *,
    tenant: Tenant,
    source_type: str,
    file_hash: str | None,
    content_hash: str | None,
    sync_key: str | None,
) -> IngestionBatch | None:
    qs = IngestionBatch.objects.filter(tenant=tenant, source_type=source_type).order_by("-uploaded_at")
    if file_hash:
        existing = qs.filter(file_hash=file_hash).first()
        if existing:
            return existing
    if content_hash:
        existing = qs.filter(content_hash=content_hash).first()
        if existing:
            return existing
    if sync_key:
        existing = qs.filter(sync_key=sync_key, status__in=["COMPLETE", "PARTIAL", "PROCESSING"]).first()
        if existing:
            return existing
    return None


def _find_duplicate_raw_record(
    *,
    tenant: Tenant,
    batch: IngestionBatch,
    source_type: str,
    row_hash: str,
    source_event_key: str,
    seen_rows: dict[str, RawRecord],
    seen_events: dict[str, RawRecord],
) -> RawRecord | None:
    if row_hash in seen_rows:
        return seen_rows[row_hash]
    if source_event_key and source_event_key in seen_events:
        return seen_events[source_event_key]

    qs = RawRecord.objects.filter(tenant=tenant, source_type=source_type).exclude(batch=batch).order_by("-created_at")
    existing = qs.filter(row_hash=row_hash).first()
    if existing:
        return existing
    if source_event_key:
        existing = qs.filter(source_event_key=source_event_key).first()
        if existing:
            return existing
    return None


def _apply_duplicate_context(
    *,
    tenant: Tenant,
    batch: IngestionBatch,
    raw: RawRecord,
    draft: ActivityDraft,
    duplicate_batch: IngestionBatch | None,
    duplicate_raw: RawRecord | None,
    source_event_key: str,
) -> None:
    if not draft.event_key:
        draft.event_key = build_activity_event_key(batch.source_type, raw.raw_payload, source_event_key)

    duplicate_activity = _find_duplicate_activity(tenant, batch, draft)

    if duplicate_batch is not None:
        flag = "DUPLICATE_TRAVEL_SYNC" if batch.source_type == "travel" else "DUPLICATE_FILE_UPLOAD"
        draft.add_issue(flag, severity="WARNING", message=f"Duplicates earlier batch {duplicate_batch.id}")
        draft.requires_reconciliation = True
        draft.duplicate_reason = "duplicate file upload" if batch.source_type != "travel" else "duplicate travel sync"

    if duplicate_raw is not None:
        in_batch = duplicate_raw.batch_id == batch.id
        flags = ["DUPLICATE_ROW_IN_BATCH"] if in_batch else ["CROSS_BATCH_DUPLICATE"]
        if batch.source_type == "sap":
            flags.append("DUPLICATE_SAP_ROW")
        elif batch.source_type == "travel":
            flags.append("DUPLICATE_TRAVEL_EVENT")
        for flag in flags:
            draft.add_issue(flag, severity="WARNING", message=f"Duplicates raw row {duplicate_raw.row_number} in batch {duplicate_raw.batch_id}")
        draft.is_duplicate = True
        draft.requires_reconciliation = True
        draft.duplicate_reason = draft.duplicate_reason or ("duplicate raw row in batch" if in_batch else "duplicate raw row across batches")

    if duplicate_activity is not None:
        draft.is_duplicate = True
        draft.requires_reconciliation = True
        draft.duplicate_reason = draft.duplicate_reason or _activity_duplicate_reason(draft, duplicate_activity)
        draft.add_issue("DOUBLE_COUNT_RISK", severity="WARNING", message=f"May duplicate activity {duplicate_activity.id}")
        if duplicate_activity.batch_id != batch.id:
            draft.add_issue("CROSS_BATCH_DUPLICATE", severity="WARNING", message=f"Duplicates activity from batch {duplicate_activity.batch_id}")
        if batch.source_type == "utility":
            draft.add_issue("DUPLICATE_BILL_ACCOUNT_PERIOD", severity="WARNING", message="Same utility account/meter/period appears earlier")
        elif batch.source_type == "sap":
            draft.add_issue("DUPLICATE_SAP_ROW", severity="WARNING", message="Same SAP activity appears earlier")
        elif batch.source_type == "travel":
            draft.add_issue("DUPLICATE_TRAVEL_EVENT", severity="WARNING", message="Same travel event appears earlier")
        draft.add_issue("REQUIRES_RECONCILIATION", severity="INFO", message="Analyst must decide whether this should be counted")
        setattr(draft, "_duplicate_of_activity", duplicate_activity)
    else:
        setattr(draft, "_duplicate_of_activity", None)

    if draft.requires_reconciliation and draft.eligibility_status == "ELIGIBLE":
        draft.eligibility_status = "NEEDS_REVIEW"
    confidence_service.apply(draft)
    if draft.requires_reconciliation and draft.confidence_level == "HIGH":
        draft.confidence_level = "MEDIUM"


def _find_duplicate_activity(
    tenant: Tenant,
    batch: IngestionBatch,
    draft: ActivityDraft,
) -> NormalizedActivity | None:
    qs = NormalizedActivity.objects.filter(tenant=tenant).order_by("-created_at")
    if draft.event_key:
        existing = qs.filter(event_key=draft.event_key).first()
        if existing:
            return existing

    if draft.activity_type and draft.normalized_quantity is not None:
        same_activity = qs.filter(
            activity_type=draft.activity_type,
            normalized_quantity=draft.normalized_quantity,
            normalized_unit=draft.normalized_unit,
        )
        if draft.facility_name:
            same_activity = same_activity.filter(facility_name=draft.facility_name)
        if draft.activity_date:
            same_activity = same_activity.filter(activity_date=draft.activity_date)
        existing = same_activity.first()
        if existing:
            return existing
    return None


def _activity_duplicate_reason(draft: ActivityDraft, duplicate: NormalizedActivity) -> str:
    if draft.source_type != duplicate.source_type:
        return "possible duplicate activity across sources"
    if draft.event_key and draft.event_key == duplicate.event_key:
        return "same source event key"
    return "similar normalized activity"
