"""Duplicate hashing and source-event-key helpers."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any


def canonicalize_payload(payload: dict) -> dict:
    """Return a stable representation for hashing raw source payloads."""
    return {
        _clean_key(key): _clean_value(value)
        for key, value in sorted((payload or {}).items(), key=lambda item: _clean_key(item[0]))
    }


def hash_payload(payload: dict) -> str:
    """Hash canonical JSON payload using sha256."""
    canonical = canonicalize_payload(payload)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def hash_file(file_bytes: bytes) -> str:
    """Hash original uploaded file bytes using sha256."""
    return hashlib.sha256(file_bytes).hexdigest()


def hash_rows_content(rows: list[dict]) -> str:
    """Hash normalized row content while ignoring row order."""
    canonical_rows = [
        json.dumps(canonicalize_payload(row), sort_keys=True, separators=(",", ":"), default=str)
        for row in rows
    ]
    encoded = json.dumps(sorted(canonical_rows), separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_source_event_key(source_type: str, raw_payload: dict) -> str:
    """Build a deterministic source-row identity key."""
    if source_type == "sap":
        return _sap_event_key(raw_payload)
    if source_type == "utility":
        return _utility_event_key(raw_payload)
    if source_type == "travel":
        return _travel_event_key(raw_payload)
    return f"{source_type}:{hash_payload(raw_payload)}"


def build_activity_event_key(source_type: str, raw_payload: dict, fallback: str | None = None) -> str:
    """Build a normalized activity identity key."""
    key = build_source_event_key(source_type, raw_payload)
    if key:
        return key
    return fallback or f"{source_type}:{hash_payload(raw_payload)}"


def _sap_event_key(payload: dict) -> str:
    document = _first(payload, "document_number", "document number", "belegnummer", "material document")
    line = _first(payload, "line_item", "line item", "zeile", "item")
    movement = _first(payload, "movement_type", "movement type", "bewegungsart")
    material = _first(payload, "material_code", "materialnummer", "material")
    posting = _first(payload, "posting_date", "posting date", "buchungsdatum")
    plant = _first(payload, "plant_code", "plant", "werk")
    quantity = _first(payload, "quantity", "menge")
    unit = _first(payload, "unit", "me", "unit of measure")
    parts = ["sap", document, line, movement, material, posting, plant, quantity, unit]
    return _join_key(parts)


def _utility_event_key(payload: dict) -> str:
    provider = _first(payload, "provider", "utility_provider")
    account = _first(payload, "account_number", "account")
    meter = _first(payload, "meter_number", "meter")
    start = _first(payload, "billing_start", "period_start")
    end = _first(payload, "billing_end", "period_end")
    usage = _first(payload, "usage_kwh", "usage", "quantity")
    unit = "kwh" if usage else _first(payload, "usage_unit", "unit")
    return _join_key(["utility", provider, account, meter, start, end, usage, unit])


def _travel_event_key(payload: dict) -> str:
    seg_type = _first(payload, "segment_type", "transport_mode", "activity_type").lower()
    trip = payload.get("_trip") if isinstance(payload.get("_trip"), dict) else {}
    employee = _first(payload, "employee_id") or _first(trip, "employee_id")
    if seg_type == "flight":
        ticket = _first(payload, "ticket_number")
        leg = _first(payload, "leg_id")
        travel_date = (_first(payload, "departure_datetime") or _first(trip, "trip_start_date"))[:10]
        origin = _first(payload, "origin")
        destination = _first(payload, "destination")
        if ticket:
            return _join_key(["travel", "flight", employee, travel_date, origin, destination, ticket, leg])
        return _join_key([
            "travel", "flight", employee, _first(payload, "departure_datetime"),
            origin, destination, _first(payload, "carrier", "vendor"), _first(payload, "flight_number"),
        ])
    if seg_type == "hotel":
        return _join_key([
            "travel", "hotel", employee, _first(payload, "vendor", "hotel_name"),
            _first(payload, "check_in_date"), _first(payload, "check_out_date"),
            _first(payload, "city"), _first(payload, "confirmation_number"),
        ])
    if seg_type in {"car_rental", "car", "rideshare", "taxi", "ground"}:
        return _join_key([
            "travel", "ground", employee,
            _first(payload, "pickup_datetime", "start_date")[:10],
            _first(payload, "pickup_city", "origin"),
            _first(payload, "dropoff_city", "destination"),
            _first(payload, "vendor"),
            _first(payload, "amount"),
        ])
    return _join_key(["travel", seg_type or "segment", employee, _first(payload, "confirmation_number"), hash_payload(payload)[:16]])


def _clean_key(key: Any) -> str:
    return str(key or "").strip().lower()


def _clean_value(value: Any):
    if value == "":
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return canonicalize_payload(value)
    if isinstance(value, list):
        return [_clean_value(item) for item in value]
    return value


def _first(payload: dict, *keys: str) -> str:
    normalized = {_clean_key(key): value for key, value in (payload or {}).items()}
    for key in keys:
        value = normalized.get(_clean_key(key))
        cleaned = _clean_value(value)
        if cleaned is not None:
            return str(cleaned).strip().lower()
    return ""


def _join_key(parts: list[str]) -> str:
    cleaned = [str(part or "").strip().lower() for part in parts if str(part or "").strip()]
    return ":".join(cleaned)
