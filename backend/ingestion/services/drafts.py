"""Data structures returned by adapters before they hit the DB.

Keeping adapters pure (returning dataclasses, not Django models) lets us unit-test
them without a database and replay them when adapter logic changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass
class ValidationIssueDraft:
    issue_code: str
    severity: str = "WARNING"  # ERROR | WARNING | INFO
    message: str = ""


@dataclass
class ActivityDraft:
    """Mirrors the persistable fields on activities.models.NormalizedActivity."""

    # Classification
    source_type: str = ""
    activity_type: str = ""
    activity_subtype: str | None = None
    scope: int | None = None
    scope_category: str | None = None

    # Eligibility & method
    eligibility_status: str = "ELIGIBLE"
    source_hierarchy_rank: int | None = None
    source_of_truth: str | None = None
    activity_basis: str | None = None
    calculation_method: str | None = None
    emission_method: str | None = None

    # Time
    activity_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    calendar_month: date | None = None
    billing_days: int | None = None

    # Location
    facility_code: str | None = None
    facility_name: str | None = None
    facility_country: str | None = None
    origin: str | None = None
    destination: str | None = None

    # Quantity
    quantity: Decimal | None = None
    unit: str | None = None
    normalized_quantity: Decimal | None = None
    normalized_unit: str | None = None
    usage_per_day: Decimal | None = None

    # Spend
    currency: str | None = None
    amount: Decimal | None = None

    # Context
    vendor: str | None = None
    cost_center: str | None = None
    reference_id: str | None = None
    event_key: str | None = None
    parent_event_key: str | None = None

    # Dedup/reversal/estimate
    is_duplicate: bool = False
    is_reversal: bool = False
    reversal_of: str | None = None
    is_estimate: bool = False
    estimate_reason: str | None = None
    requires_reconciliation: bool = False

    # Emissions
    emission_factor: Decimal | None = None
    emission_factor_source: str | None = None
    co2e_kg: Decimal | None = None

    # Quality
    data_quality_score: int = 100
    confidence_level: str = "HIGH"
    method_confidence: Decimal | None = None
    flags: list[str] = field(default_factory=list)
    field_provenance: dict[str, Any] = field(default_factory=dict)

    # Side channel
    issues: list[ValidationIssueDraft] = field(default_factory=list)

    def add_flag(self, code: str) -> None:
        if code not in self.flags:
            self.flags.append(code)

    def add_issue(self, code: str, severity: str = "WARNING", message: str = "") -> None:
        self.add_flag(code)
        self.issues.append(ValidationIssueDraft(issue_code=code, severity=severity, message=message or code))

    def set_provenance(
        self,
        field_name: str,
        method: str,
        *,
        source_field: str | None = None,
        rule: str | None = None,
        confidence: float | None = None,
        reason: str | None = None,
        note: str | None = None,
    ) -> None:
        entry: dict[str, Any] = {"method": method}
        if source_field is not None:
            entry["source_field"] = source_field
        if rule is not None:
            entry["rule"] = rule
        if confidence is not None:
            entry["confidence"] = confidence
        if reason is not None:
            entry["reason"] = reason
        if note is not None:
            entry["note"] = note
        self.field_provenance[field_name] = entry


@dataclass
class AdapterRowResult:
    """One source row, optionally producing N activity drafts."""

    raw_payload: dict[str, Any]
    parse_status: str = "PARSED"  # PARSED | FAILED | EXCLUDED
    eligibility_status: str | None = None
    exclusion_reason: str | None = None
    error_message: str | None = None
    activities: list[ActivityDraft] = field(default_factory=list)


@dataclass
class AdapterBatchResult:
    """Full result of running an adapter on a batch of rows."""

    rows: list[AdapterRowResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
