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
    "is_duplicate", "is_reversal", "reversal_of",
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
    notes: str = "",
) -> IngestionBatch:
    """Create the batch and all child rows in one transaction."""
    batch = IngestionBatch.objects.create(
        tenant=tenant,
        source_type=source_type,
        ingestion_method=ingestion_method,
        original_filename=original_filename,
        api_sync_range_start=api_sync_range_start,
        api_sync_range_end=api_sync_range_end,
        status="PROCESSING",
        notes=notes,
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

    for row_idx, row_result in enumerate(adapter_result.rows):
        raw = RawRecord.objects.create(
            tenant=tenant,
            batch=batch,
            source_type=source_type,
            row_number=row_idx + 1,
            raw_payload=_json_safe(row_result.raw_payload),
            parse_status=row_result.parse_status,
            eligibility_status=row_result.eligibility_status,
            exclusion_reason=row_result.exclusion_reason,
            error_message=row_result.error_message,
        )
        parse_counter[row_result.parse_status] += 1
        if row_result.eligibility_status:
            elig_counter[row_result.eligibility_status] += 1

        for draft in row_result.activities:
            kwargs = _draft_to_kwargs(draft)
            # Decimal/date sanitation happens inside Django; nothing to do here.
            activity = NormalizedActivity.objects.create(
                tenant=tenant, batch=batch, raw_record=raw, **kwargs,
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
