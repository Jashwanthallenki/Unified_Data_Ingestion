"""Confidence scoring per the deduction table in PLAN/MODEL/DECISIONS."""
from __future__ import annotations

from .drafts import ActivityDraft


# (flag_code, deduction). A row's deduction = sum over flags it carries.
DEDUCTIONS: dict[str, int] = {
    # Generic
    "MISSING_REQUIRED_FIELD": 20,
    "LOW_CONFIDENCE": 0,  # marker, no extra deduction
    "LLM_SUGGESTED_FIELD": 10,
    "LLM_SUGGESTION_FAILED": 5,
    "MISSING_SOURCE_REFERENCE": 10,

    # SAP
    "UNKNOWN_PLANT_CODE": 10,
    "UNKNOWN_MATERIAL_CODE": 10,
    "UNKNOWN_UNIT": 15,
    "UNSUPPORTED_MOVEMENT_TYPE": 15,
    "MISSING_POSTING_DATE": 15,
    "MISSING_QUANTITY": 20,
    "MISSING_UNIT": 15,
    "MISSING_FACILITY_MAPPING": 15,
    "NEGATIVE_QUANTITY": 10,
    "ZERO_QUANTITY": 10,
    "SUSPICIOUS_HIGH_QUANTITY": 10,
    "DUPLICATE_DOCUMENT": 20,
    "CROSS_BATCH_DUPLICATE": 20,
    "PURCHASE_NOT_CONSUMPTION": 5,
    "DUPLICATE_FUEL_SOURCE": 15,
    "GERMAN_HEADER_MAPPING_USED": 0,  # info, no deduction
    "UNIT_DENSITY_CONVERSION_REQUIRED": 5,
    "SCRAP_REQUIRES_REVIEW": 10,
    "REVERSAL_ROW": 0,  # reversal handled by net, not deducted from confidence
    "STOCK_TRANSFER_ROW": 0,  # excluded entirely
    "INVENTORY_ADJUSTMENT_ROW": 0,

    # Utility
    "MISSING_METER_NUMBER": 10,
    "MISSING_ACCOUNT_NUMBER": 5,
    "MISSING_USAGE_KWH": 20,
    "TOTAL_AMOUNT_ONLY": 25,
    "AMOUNT_ONLY_NO_USAGE": 25,
    "ZERO_KWH": 5,
    "NEGATIVE_KWH": 10,
    "INVALID_BILLING_PERIOD": 20,
    "BILLING_END_BEFORE_START": 20,
    "BILLING_PERIOD_TOO_LONG": 5,
    "BILLING_PERIOD_TOO_SHORT": 5,
    "OVERLAPPING_BILLING_PERIOD": 10,
    "DUPLICATE_BILL_ACCOUNT_PERIOD": 20,
    "ESTIMATED_READING": 10,
    "MISSING_READING_TYPE": 5,
    "POSSIBLE_AMENDED_BILL": 10,
    "USAGE_SPIKE_AFTER_DAY_NORMALIZATION": 5,
    "MARKET_BASED_SCOPE2_EVIDENCE_MISSING": 10,
    "MULTIPLE_METER_SITE": 0,

    # Travel
    "MISSING_FLIGHT_DISTANCE": 20,
    "MISSING_ORIGIN_DESTINATION": 20,
    "DISTANCE_ESTIMATED": 5,
    "RAIL_DISTANCE_ESTIMATED": 5,
    "CABIN_CLASS_MISSING": 5,
    "UNKNOWN_CABIN_CLASS": 5,
    "POSSIBLE_CODESHARE_DUPLICATE": 10,
    "MISSING_HOTEL_NIGHTS": 15,
    "MISSING_CHECKOUT": 20,
    "ZERO_ROOM_NIGHTS": 10,
    "HOTEL_LOCATION_MISSING": 10,
    "BUNDLED_TRAVEL_PACKAGE": 15,
    "RENTAL_CAR_DOUBLE_COUNT_RISK": 5,
    "GROUND_TRANSPORT_NO_ROUTING": 10,
    "AMOUNT_ONLY_TRAVEL_ROW": 15,
    "SPEND_BASED_FALLBACK": 15,
}

# Per-method base confidence ceilings.
METHOD_CEILING: dict[str, int] = {
    "fuel_based": 100,
    "distance_based": 95,
    "room_night_based": 90,
    "location_based_scope2": 95,
    "market_based_scope2": 85,
    "supplier_specific": 95,
    "average_data": 70,
    "spend_based": 60,
}


def score(activity: ActivityDraft) -> tuple[int, str]:
    """Return (data_quality_score 0..100, confidence_level HIGH/MEDIUM/LOW/FAILED)."""
    method = (activity.calculation_method or activity.emission_method or "").lower()
    base = METHOD_CEILING.get(method, 100)
    deduction = 0
    for flag in activity.flags:
        deduction += DEDUCTIONS.get(flag, 0)
    score_val = max(0, base - deduction)
    if score_val >= 80:
        level = "HIGH"
    elif score_val >= 50:
        level = "MEDIUM"
    elif score_val >= 30:
        level = "LOW"
    else:
        level = "FAILED"
    return score_val, level


def apply(activity: ActivityDraft) -> None:
    """Mutate the activity to set data_quality_score + confidence_level."""
    activity.data_quality_score, activity.confidence_level = score(activity)
