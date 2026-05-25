"""Unit normalization and emission factor application."""
from __future__ import annotations

from decimal import Decimal

from .drafts import ActivityDraft
from .lookup_context import LookupContext


def normalize_unit(activity: ActivityDraft, ctx: LookupContext) -> None:
    """Set normalized_quantity + normalized_unit from raw quantity + unit + UnitMapping."""
    if activity.quantity is None or activity.unit is None:
        return
    src_unit = activity.unit.upper()
    mapping = ctx.unit_mappings.get(src_unit)
    if mapping is None:
        activity.add_issue("UNKNOWN_UNIT", severity="ERROR", message=f"Unknown unit code: {activity.unit}")
        return
    activity.normalized_unit = mapping.normalized_unit
    activity.normalized_quantity = activity.quantity * mapping.conversion_factor
    activity.set_provenance(
        "normalized_unit",
        method="RULE_BASED",
        rule=f"UnitMapping:{src_unit}->{mapping.normalized_unit}",
        confidence=1.0,
    )
    activity.set_provenance(
        "normalized_quantity",
        method="RULE_BASED",
        rule=f"UnitMapping:×{mapping.conversion_factor}",
        confidence=1.0,
    )


def apply_emission_factor(
    activity: ActivityDraft,
    ctx: LookupContext,
    *,
    region: str | None = None,
) -> None:
    """Look up an emission factor and compute co2e_kg."""
    method = activity.calculation_method or activity.emission_method
    subtype = activity.activity_subtype
    if method == "spend_based":
        # use currency as unit and subtype to find a per-currency factor
        ef = ctx.find_emission_factor(
            activity_type="spend_based",
            activity_subtype=subtype or "general",
            method="spend_based",
            unit=activity.currency or "",
            region=region,
        )
        if ef is None and subtype:
            # fall back to "general" subtype in same currency
            ef = ctx.find_emission_factor(
                activity_type="spend_based",
                activity_subtype="general",
                method="spend_based",
                unit=activity.currency or "",
                region=region,
            )
        if ef and activity.amount is not None:
            activity.emission_factor = ef.factor
            activity.emission_factor_source = f"{ef.source} ({ef.version})"
            activity.co2e_kg = activity.amount * ef.factor
            activity.set_provenance(
                "co2e_kg",
                method="RULE_BASED",
                rule=f"spend×{ef.factor} {ef.factor_unit}/{ef.unit}",
                confidence=0.5,
            )
        return

    # Physical-unit method
    if activity.normalized_quantity is None or not activity.normalized_unit:
        return
    ef = ctx.find_emission_factor(
        activity_type=activity.activity_type,
        activity_subtype=subtype,
        method=method,
        unit=activity.normalized_unit,
        region=region,
    )
    if ef is None:
        # Try without subtype as fallback (e.g. hotel/standard)
        ef = ctx.find_emission_factor(
            activity_type=activity.activity_type,
            activity_subtype=None,
            method=method,
            unit=activity.normalized_unit,
            region=region,
        )
    if ef is None:
        return
    activity.emission_factor = ef.factor
    activity.emission_factor_source = f"{ef.source} ({ef.version})"
    activity.co2e_kg = activity.normalized_quantity * ef.factor
    activity.set_provenance(
        "co2e_kg",
        method="RULE_BASED",
        rule=f"EF {ef.activity_type}/{ef.activity_subtype}:{ef.factor} {ef.factor_unit}/{ef.unit}",
        confidence=0.95,
    )


def classify_flight_subtype(distance_km: Decimal | float | None, cabin_lower: str) -> str:
    """Map distance + cabin class to a flight subtype the EF table knows."""
    d = float(distance_km or 0)
    long_haul = d >= 3700
    cabin = (cabin_lower or "").lower()
    if cabin in ("first",):
        return "long_haul_first" if long_haul else "short_haul_business"
    if cabin in ("business",):
        return "long_haul_business" if long_haul else "short_haul_business"
    if cabin in ("premium_economy", "premium economy"):
        return "long_haul_premium_economy" if long_haul else "short_haul_economy"
    return "long_haul_economy" if long_haul else "short_haul_economy"


CABIN_CLASS_MAP = {
    # Economy
    "Y": "economy", "B": "economy", "M": "economy", "H": "economy", "Q": "economy",
    "K": "economy", "L": "economy", "U": "economy", "T": "economy", "X": "economy",
    "V": "economy", "N": "economy", "G": "economy", "R": "economy",
    # Premium economy
    "W": "premium_economy", "S": "premium_economy", "E": "premium_economy",
    # Business
    "C": "business", "D": "business", "I": "business", "J": "business", "Z": "business",
    # First
    "F": "first", "A": "first", "P": "first",
}


def cabin_label(code: str | None, *, default: str = "economy") -> tuple[str, bool]:
    """Return (canonical label, was_unknown). default applied when code is unknown."""
    if not code:
        return default, True
    label = CABIN_CLASS_MAP.get(code.strip().upper())
    if label is None:
        return default, True
    return label, False
