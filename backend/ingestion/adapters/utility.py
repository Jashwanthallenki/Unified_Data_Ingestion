"""Utility electricity adapter.

Takes CSV rows representing utility-portal exports and produces NormalizedActivity
drafts with calendar-month pro-rata, estimated-reading handling, overlap detection,
and gas rejection.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..services import confidence as confidence_service
from ..services import normalization
from ..services.drafts import ActivityDraft, AdapterBatchResult, AdapterRowResult
from ..services.lookup_context import LookupContext
from ..services.utils import calendar_month_overlaps, parse_date, parse_decimal, safe_str


NON_CONSUMPTION_CHARGES = {"tax", "late_fee", "fee", "payment", "deposit", "adjustment", "refund"}


def adapt_utility(rows: list[dict], ctx: LookupContext) -> AdapterBatchResult:
    """Process utility electricity rows."""
    result = AdapterBatchResult(metadata={"source": "utility_electricity"})

    # First pass: collect period intervals per meter for overlap detection.
    intervals: dict[tuple[str, str], list[tuple[date, date, int]]] = {}
    for idx, raw in enumerate(rows):
        account = safe_str(raw.get("account_number")).upper()
        meter = safe_str(raw.get("meter_number")).upper()
        bs = parse_date(safe_str(raw.get("billing_start")))
        be = parse_date(safe_str(raw.get("billing_end")))
        if account and meter and bs and be and bs <= be:
            intervals.setdefault((account, meter), []).append((bs, be, idx))

    # Multi-meter sites
    meters_per_address: dict[str, set[str]] = {}
    for raw in rows:
        addr = safe_str(raw.get("service_address")).lower()
        m = safe_str(raw.get("meter_number")).upper()
        if addr and m:
            meters_per_address.setdefault(addr, set()).add(m)

    seen_period_key: set[tuple[str, str, str, str]] = set()

    for idx, raw in enumerate(rows):
        result.rows.append(_process_row(raw, ctx, idx, intervals, meters_per_address, seen_period_key))

    return result


def _process_row(
    raw: dict,
    ctx: LookupContext,
    idx: int,
    intervals: dict[tuple[str, str], list[tuple[date, date, int]]],
    meters_per_address: dict[str, set[str]],
    seen_period_key: set,
) -> AdapterRowResult:
    provider = safe_str(raw.get("provider"))
    account_number = safe_str(raw.get("account_number")).upper()
    meter_number = safe_str(raw.get("meter_number")).upper()
    service_address = safe_str(raw.get("service_address"))
    charge_type = safe_str(raw.get("charge_type")).lower()
    bill_type = safe_str(raw.get("bill_type")).lower()
    reading_type = safe_str(raw.get("reading_type")).lower()
    tariff = safe_str(raw.get("tariff"))
    notes = safe_str(raw.get("notes"))
    currency = safe_str(raw.get("currency")).upper() or None
    usage_kwh = parse_decimal(raw.get("usage_kwh"))
    demand_kw = parse_decimal(raw.get("demand_kw"))
    total_amount = parse_decimal(raw.get("total_amount"))
    billing_start = parse_date(safe_str(raw.get("billing_start")))
    billing_end = parse_date(safe_str(raw.get("billing_end")))

    # Reject gas rows from electricity ingestion
    if bill_type == "gas" or (tariff and "gas" in tariff.lower()):
        return AdapterRowResult(
            raw_payload=raw, parse_status="EXCLUDED",
            eligibility_status="EXCLUDED",
            exclusion_reason="gas_row_rejected_from_electricity",
        )

    # Charge-type filter
    if charge_type in NON_CONSUMPTION_CHARGES:
        reason_map = {
            "tax": "tax_only_utility_row",
            "late_fee": "late_fee_only_row",
            "fee": "fee_only_row",
            "payment": "payment_only_row",
            "deposit": "deposit_row",
            "adjustment": "amount_only_adjustment",
            "refund": "refund_row",
        }
        return AdapterRowResult(
            raw_payload=raw, parse_status="EXCLUDED",
            eligibility_status="NOT_RELEVANT",
            exclusion_reason=reason_map.get(charge_type, f"non_consumption_{charge_type}"),
        )

    activity_base = _new_utility_draft(
        provider, account_number, meter_number, service_address,
        billing_start, billing_end, usage_kwh, demand_kw, total_amount, currency,
        tariff, reading_type, notes,
    )

    # Resolve meter → facility
    meter_key = (provider.lower(), account_number, meter_number)
    meter_lookup = ctx.meters.get(meter_key) if all(meter_key) else None
    if meter_lookup is None and account_number and meter_number:
        # Try fuzzy: any provider matching account+meter
        for k, v in ctx.meters.items():
            if k[1] == account_number and k[2] == meter_number:
                meter_lookup = v
                break
    if meter_lookup:
        activity_base.facility_code = meter_lookup.facility_code
        activity_base.facility_name = meter_lookup.facility_name
        activity_base.facility_country = meter_lookup.facility_country
        activity_base.set_provenance(
            "facility_name", method="RULE_BASED",
            rule=f"MeterFacilityLookup:{meter_number}->{meter_lookup.facility_name}",
            confidence=0.95,
        )
    else:
        activity_base.add_issue("UNKNOWN_FACILITY", severity="WARNING",
                                message=f"Meter {meter_number} / account {account_number} not in lookup")

    # Required field flags
    if not provider:
        activity_base.add_issue("MISSING_REQUIRED_FIELD", severity="WARNING",
                                 message="Provider missing")
    if not meter_number:
        activity_base.add_issue("MISSING_METER_NUMBER", severity="WARNING",
                                 message="Meter number missing")
    if not account_number:
        activity_base.add_issue("MISSING_ACCOUNT_NUMBER", severity="WARNING",
                                 message="Account number missing")
    if not reading_type:
        activity_base.add_issue("MISSING_READING_TYPE", severity="WARNING",
                                 message="Reading type not specified")

    # Multi-meter site info
    addr = service_address.lower()
    if addr and len(meters_per_address.get(addr, set())) > 1:
        activity_base.add_flag("MULTIPLE_METER_SITE")

    # Period sanity
    if billing_start is None or billing_end is None:
        activity_base.add_issue("INVALID_BILLING_PERIOD", severity="ERROR",
                                 message="Billing start or end missing")
        activity_base.eligibility_status = "NEEDS_REVIEW"
    elif billing_end < billing_start:
        activity_base.add_issue("BILLING_END_BEFORE_START", severity="ERROR",
                                 message=f"end {billing_end} is before start {billing_start}")
        activity_base.eligibility_status = "NEEDS_REVIEW"
    else:
        billing_days = (billing_end - billing_start).days + 1
        activity_base.billing_days = billing_days
        if billing_days > 40:
            activity_base.add_issue("BILLING_PERIOD_TOO_LONG", severity="WARNING",
                                     message=f"{billing_days} days")
        elif billing_days < 25:
            activity_base.add_issue("BILLING_PERIOD_TOO_SHORT", severity="WARNING",
                                     message=f"{billing_days} days")

    # Amount-only / missing usage handling
    if usage_kwh is None:
        if total_amount is not None and total_amount != 0:
            activity_base.add_issue("TOTAL_AMOUNT_ONLY", severity="WARNING",
                                     message="No usage_kwh; total_amount only — spend-based fallback")
            activity_base.calculation_method = "spend_based"
            activity_base.emission_method = "spend_based"
            activity_base.activity_subtype = "electricity"
            activity_base.is_estimate = True
            activity_base.estimate_reason = "Amount-only utility row"
            activity_base.eligibility_status = "NEEDS_REVIEW"
        else:
            activity_base.add_issue("MISSING_USAGE_KWH", severity="ERROR",
                                     message="Both usage_kwh and total_amount are missing")
            activity_base.eligibility_status = "FAILED"
    elif usage_kwh == 0:
        activity_base.add_issue("ZERO_KWH", severity="INFO", message="Usage is zero")
        activity_base.eligibility_status = "NEEDS_REVIEW"
    elif usage_kwh < 0:
        activity_base.add_issue("NEGATIVE_KWH", severity="WARNING",
                                 message="Negative usage — likely refund/correction")
        activity_base.eligibility_status = "NEEDS_REVIEW"

    # Estimated readings
    if reading_type == "estimated":
        activity_base.is_estimate = True
        activity_base.estimate_reason = "Provider reported reading_type=estimated"
        activity_base.add_issue("ESTIMATED_READING", severity="INFO",
                                 message="Provider marked reading as estimated; confidence capped at 70")

    # Duplicate (same account+meter+period)
    period_key = (account_number, meter_number,
                  billing_start.isoformat() if billing_start else "",
                  billing_end.isoformat() if billing_end else "")
    if all(period_key) and period_key in seen_period_key:
        activity_base.add_issue("DUPLICATE_BILL_ACCOUNT_PERIOD", severity="WARNING",
                                 message="Same account+meter+period already seen")
    else:
        if all(period_key):
            seen_period_key.add(period_key)

    # Overlap detection
    if billing_start and billing_end and meter_key[1] and meter_key[2]:
        others = intervals.get((account_number, meter_number), [])
        for (bs, be, jdx) in others:
            if jdx == idx:
                continue
            if bs <= billing_end and be >= billing_start:
                activity_base.add_issue("OVERLAPPING_BILLING_PERIOD", severity="WARNING",
                                         message=f"Overlaps another row (rows {idx+1} and {jdx+1})")
                activity_base.add_flag("POSSIBLE_AMENDED_BILL")
                activity_base.requires_reconciliation = True
                break

    # Build emission-relevant outputs.
    # If usage_kwh is None and we're spend-based, emit single activity.
    if usage_kwh is None:
        activity_base.activity_type = "electricity_usage"
        activity_base.activity_basis = "spend_only"
        activity_base.amount = total_amount
        activity_base.activity_date = billing_end or billing_start
        _finalize_activity(activity_base, ctx)
        return AdapterRowResult(
            raw_payload=raw, parse_status="PARSED",
            eligibility_status=activity_base.eligibility_status,
            activities=[activity_base],
        )

    # Pro-rate kWh across calendar months when both dates are present.
    activities: list[ActivityDraft] = []
    if billing_start and billing_end and billing_start <= billing_end:
        total_days = (billing_end - billing_start).days + 1
        for cm_start, days_in_m in calendar_month_overlaps(billing_start, billing_end):
            child = _clone(activity_base)
            child.calendar_month = cm_start
            ratio = Decimal(days_in_m) / Decimal(total_days)
            child.normalized_quantity = (usage_kwh * ratio).quantize(Decimal("0.0001"))
            child.quantity = (usage_kwh * ratio).quantize(Decimal("0.0001"))
            child.unit = "kWh"
            child.normalized_unit = "kWh"
            child.billing_days = days_in_m
            child.usage_per_day = (child.normalized_quantity / Decimal(days_in_m)).quantize(Decimal("0.0001"))
            child.period_start = max(billing_start, cm_start)
            from calendar import monthrange
            last_dom = monthrange(cm_start.year, cm_start.month)[1]
            child.period_end = min(billing_end, date(cm_start.year, cm_start.month, last_dom))
            child.activity_date = child.period_end
            child.activity_type = "electricity_usage"
            child.activity_subtype = "grid"
            child.calculation_method = "location_based_scope2"
            child.emission_method = "location_based_scope2"
            child.activity_basis = "metered_usage" if not child.is_estimate else "estimated_meter_usage"
            child.scope = 2
            child.scope_category = "2 purchased electricity"
            child.source_of_truth = "utility_meter"
            child.source_hierarchy_rank = 1 if not child.is_estimate else 2
            child.set_provenance(
                "calendar_month", method="RULE_BASED",
                rule=f"BillingProRata:{billing_start.isoformat()}..{billing_end.isoformat()}:{days_in_m}/{total_days}",
                confidence=1.0,
            )
            _finalize_activity(child, ctx)
            activities.append(child)
    else:
        # Could not pro-rate; emit single record using period_end as activity_date
        activity_base.activity_date = billing_end or billing_start
        activity_base.normalized_quantity = usage_kwh
        activity_base.unit = "kWh"
        activity_base.normalized_unit = "kWh"
        activity_base.activity_type = "electricity_usage"
        activity_base.activity_subtype = "grid"
        activity_base.calculation_method = "location_based_scope2"
        activity_base.emission_method = "location_based_scope2"
        activity_base.scope = 2
        activity_base.scope_category = "2 purchased electricity"
        _finalize_activity(activity_base, ctx)
        activities.append(activity_base)

    return AdapterRowResult(
        raw_payload=raw, parse_status="PARSED",
        eligibility_status=activities[0].eligibility_status if activities else "NEEDS_REVIEW",
        activities=activities,
    )


def _new_utility_draft(
    provider: str, account: str, meter: str, service_address: str,
    billing_start: date | None, billing_end: date | None,
    usage_kwh: Decimal | None, demand_kw: Decimal | None,
    total_amount: Decimal | None, currency: str | None,
    tariff: str, reading_type: str, notes: str,
) -> ActivityDraft:
    a = ActivityDraft(source_type="utility")
    a.vendor = provider or None
    a.reference_id = f"{account or ''}/{meter or ''}".strip("/") or None
    a.period_start = billing_start
    a.period_end = billing_end
    a.quantity = usage_kwh
    a.unit = "kWh" if usage_kwh is not None else None
    a.amount = total_amount
    a.currency = currency
    a.event_key = (
        f"utility:{provider}:{account}:{meter}:"
        f"{billing_start.isoformat() if billing_start else '-'}:"
        f"{billing_end.isoformat() if billing_end else '-'}"
    ) if provider and account and meter else None
    a.set_provenance("quantity",
                     method="DIRECT" if usage_kwh is not None else "MISSING",
                     source_field="usage_kwh",
                     confidence=1.0 if usage_kwh is not None else 0.0)
    a.set_provenance("period_start", method="DIRECT" if billing_start else "MISSING", source_field="billing_start")
    a.set_provenance("period_end", method="DIRECT" if billing_end else "MISSING", source_field="billing_end")
    return a


def _clone(a: ActivityDraft) -> ActivityDraft:
    """Shallow clone for pro-rated child records — sharing flags + provenance is fine."""
    import copy
    c = copy.deepcopy(a)
    return c


def _finalize_activity(activity: ActivityDraft, ctx: LookupContext) -> None:
    if activity.normalized_quantity is None and activity.quantity is not None and activity.normalized_unit is None:
        normalization.normalize_unit(activity, ctx)
    region_hint = activity.facility_country or None
    normalization.apply_emission_factor(activity, ctx, region=region_hint)
    confidence_service.apply(activity)
    if activity.is_estimate:
        activity.data_quality_score = min(activity.data_quality_score, 70)
        if activity.data_quality_score >= 80:
            activity.confidence_level = "MEDIUM"
        elif activity.data_quality_score >= 50:
            activity.confidence_level = "MEDIUM"
        elif activity.data_quality_score >= 30:
            activity.confidence_level = "LOW"
        else:
            activity.confidence_level = "FAILED"
