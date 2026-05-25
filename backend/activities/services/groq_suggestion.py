"""Groq-assisted suggestion layer.

Used only for low-confidence rows (data_quality_score 30..49) where deterministic
mapping has failed. Never used to generate numeric values, dates, identifiers, or
distances — those must come from source data or trusted rules.

If GROQ_API_KEY is not configured, this service silently returns None and the row
falls through to manual analyst review.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from activities.models import GroqSuggestionCache, NormalizedActivity

logger = logging.getLogger(__name__)

# Fields the LLM is allowed to suggest values for.
ALLOWED_FIELDS = {
    "activity_subtype",     # diesel/petrol/natural_gas/...
    "fuel_type",            # synonym treated as activity_subtype
    "scope_category",       # e.g. "3.6 business travel"
    "spend_category",       # office_supplies / hotel / ...
    "is_esg_relevant",      # boolean text classification
    "review_explanation",   # human-readable why low confidence
    "client_followup",      # what to ask the client
}

# Fields the LLM must never invent.
FORBIDDEN_FIELDS = {
    "quantity", "normalized_quantity", "co2e_kg", "emission_factor",
    "amount", "distance_km", "usage_kwh", "hotel_nights", "room_nights",
    "activity_date", "period_start", "period_end", "calendar_month",
    "reference_id", "event_key", "document_number", "ticket_number",
    "confirmation_number", "invoice_number", "bill_number",
}


SYSTEM_PROMPT = (
    "You are an ESG data analyst assistant. You help interpret low-confidence rows in an "
    "enterprise ESG data pipeline. Your role is text-domain reasoning only: classify "
    "ambiguous material descriptions, suggest spend categories, judge ESG relevance, and "
    "explain why a row has low confidence. "
    "You MUST NOT generate numeric values, dates, identifiers, distances, or document "
    "numbers. Those come from source data or deterministic rules. "
    "Return STRICT JSON ONLY in the schema described below. Do not include prose outside "
    "the JSON. If you cannot make a useful suggestion, return an empty `suggestions` "
    "array. Confidence values must be between 0.0 and 1.0."
)


JSON_SCHEMA_DESCRIPTION = (
    "{\n"
    '  "suggestions": [\n'
    "    {\n"
    '      "field": "activity_subtype | fuel_type | scope_category | spend_category | '
    'is_esg_relevant | review_explanation | client_followup",\n'
    '      "suggested_value": <string or boolean>,\n'
    '      "confidence": <float 0..1>,\n'
    '      "reason": <string explaining the inference>\n'
    "    }\n"
    "  ],\n"
    '  "notes": [<string>]\n'
    "}"
)


@dataclass
class GroqSuggestionResult:
    ok: bool
    suggestions: list[dict[str, Any]]
    notes: list[str]
    error: str | None = None
    cached: bool = False
    model_used: str | None = None


def _build_user_prompt(
    *,
    source_type: str,
    raw_payload: dict[str, Any],
    partial_record: dict[str, Any],
    missing_fields: list[str],
    flags: list[str],
    lookup_hints: dict[str, Any] | None,
) -> str:
    parts = [
        f"Source type: {source_type}",
        f"Validation flags: {flags}",
        f"Missing or low-confidence fields: {missing_fields}",
        "",
        "Raw source row (as ingested):",
        json.dumps(raw_payload, indent=2, default=str),
        "",
        "Partial normalized record (what we have so far):",
        json.dumps(partial_record, indent=2, default=str),
    ]
    if lookup_hints:
        parts.append("")
        parts.append("Available lookup context:")
        parts.append(json.dumps(lookup_hints, indent=2, default=str))
    parts.extend([
        "",
        "Allowed suggestion fields: " + ", ".join(sorted(ALLOWED_FIELDS)),
        "Forbidden fields (NEVER suggest values for these): " + ", ".join(sorted(FORBIDDEN_FIELDS)),
        "",
        "Respond with strict JSON matching this schema and nothing else:",
        JSON_SCHEMA_DESCRIPTION,
    ])
    return "\n".join(parts)


def _cache_key(raw_record_id: str, missing_fields: list[str]) -> str:
    payload = f"{raw_record_id}|{','.join(sorted(missing_fields))}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def suggest_for_activity(activity: NormalizedActivity) -> GroqSuggestionResult:
    """Produce suggestions for one low-confidence activity. Returns ok=False on any failure."""
    if not settings.GROQ_API_KEY:
        return GroqSuggestionResult(
            ok=False, suggestions=[], notes=["GROQ_API_KEY not configured"], error="missing_api_key",
        )

    raw_record = activity.raw_record
    missing_fields = _identify_missing_fields(activity)
    cache_key = _cache_key(str(raw_record.id), missing_fields)
    cached = GroqSuggestionCache.objects.filter(
        raw_record=raw_record, missing_fields_hash=cache_key,
    ).first()
    if cached:
        data = cached.response_json
        return GroqSuggestionResult(
            ok=True,
            suggestions=data.get("suggestions", []),
            notes=data.get("notes", []),
            cached=True,
            model_used=cached.model_used,
        )

    # Build prompt
    lookup_hints = _build_lookup_hints(activity)
    user_prompt = _build_user_prompt(
        source_type=activity.source_type,
        raw_payload=raw_record.raw_payload or {},
        partial_record={
            "activity_type": activity.activity_type,
            "activity_subtype": activity.activity_subtype,
            "facility_name": activity.facility_name,
            "facility_country": activity.facility_country,
            "vendor": activity.vendor,
            "quantity": str(activity.quantity) if activity.quantity is not None else None,
            "unit": activity.unit,
            "normalized_unit": activity.normalized_unit,
            "amount": str(activity.amount) if activity.amount is not None else None,
            "currency": activity.currency,
            "calculation_method": activity.calculation_method,
            "data_quality_score": activity.data_quality_score,
            "confidence_level": activity.confidence_level,
        },
        missing_fields=missing_fields,
        flags=list(activity.flags or []),
        lookup_hints=lookup_hints,
    )

    try:
        from groq import Groq

        client = Groq(api_key=settings.GROQ_API_KEY, timeout=settings.GROQ_TIMEOUT_S)
        completion = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=800,
        )
        raw_content = completion.choices[0].message.content or "{}"
    except Exception as exc:  # any Groq SDK/HTTP/timeout error
        logger.warning("Groq suggestion call failed: %s", exc)
        return GroqSuggestionResult(
            ok=False, suggestions=[], notes=[], error=str(exc)[:300],
        )

    # Parse and validate response
    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        logger.warning("Groq returned invalid JSON: %s", exc)
        return GroqSuggestionResult(
            ok=False, suggestions=[], notes=[], error=f"invalid_json: {exc}",
        )

    suggestions = data.get("suggestions") or []
    notes = data.get("notes") or []
    # Filter out any suggestions for forbidden fields.
    filtered: list[dict[str, Any]] = []
    for s in suggestions:
        if not isinstance(s, dict):
            continue
        field = (s.get("field") or "").strip().lower()
        if field in FORBIDDEN_FIELDS:
            notes.append(f"Dropped forbidden field suggestion: {field}")
            continue
        if field not in ALLOWED_FIELDS:
            notes.append(f"Dropped unsupported field suggestion: {field}")
            continue
        try:
            conf = float(s.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        filtered.append({
            "field": field,
            "suggested_value": s.get("suggested_value"),
            "confidence": max(0.0, min(1.0, conf)),
            "reason": str(s.get("reason") or "")[:500],
            "method": "LLM_SUGGESTED",
        })

    out_data = {"suggestions": filtered, "notes": notes}
    # Cache for replay
    GroqSuggestionCache.objects.update_or_create(
        raw_record=raw_record,
        missing_fields_hash=cache_key,
        defaults={"response_json": out_data, "model_used": settings.GROQ_MODEL},
    )

    return GroqSuggestionResult(
        ok=True,
        suggestions=filtered,
        notes=notes,
        model_used=settings.GROQ_MODEL,
    )


def _identify_missing_fields(activity: NormalizedActivity) -> list[str]:
    missing: list[str] = []
    if not activity.activity_subtype:
        missing.append("activity_subtype")
    if not activity.facility_name and activity.source_type in ("sap", "utility"):
        missing.append("facility_name")
    if not activity.scope_category:
        missing.append("scope_category")
    if activity.confidence_level in ("LOW", "FAILED"):
        missing.append("review_explanation")
    return missing


def _build_lookup_hints(activity: NormalizedActivity) -> dict[str, Any]:
    """Provide the LLM with a tiny slice of relevant lookup context (no full dumps)."""
    hints: dict[str, Any] = {}
    raw = activity.raw_record.raw_payload or {}
    material_desc = (
        raw.get("material_description")
        or raw.get("Materialkurztext")
        or raw.get("Material Description")
        or ""
    )
    if material_desc:
        hints["material_description"] = material_desc
    if activity.source_type == "sap":
        hints["common_fuel_types"] = ["diesel", "petrol", "natural_gas", "heating_oil"]
        hints["common_spend_categories"] = ["office_supplies", "chemicals", "maintenance", "general"]
    elif activity.source_type == "travel":
        hints["valid_scope_categories"] = ["3.6 business travel", "3.7 employee commuting"]
    return hints
