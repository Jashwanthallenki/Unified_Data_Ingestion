"""Travel adapter.

Takes Concur/Navan-shaped trip JSON and produces NormalizedActivity drafts per
segment, handling cancellations, codeshare dedup, leg grouping, cabin class mapping,
distance estimation (haversine via airport lookup), hotel room-nights, bundled
packages, and spend-based fallbacks.

The raw_payload for each AdapterRowResult is the *segment* (not the trip), with
trip-level fields denormalized in.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from ..services import confidence as confidence_service
from ..services import normalization
from ..services.drafts import ActivityDraft, AdapterBatchResult, AdapterRowResult
from ..services.lookup_context import LookupContext
from ..services.utils import haversine_km, parse_date, parse_decimal, safe_str


EXCLUDED_STATUSES = {"cancelled", "refunded", "voided", "no_show", "no-show"}


def adapt_travel(trips: list[dict], ctx: LookupContext) -> AdapterBatchResult:
    """Flatten trips→segments and produce per-segment drafts."""
    result = AdapterBatchResult(metadata={"source": "travel"})

    # Flatten segments with trip metadata.
    segments: list[dict] = []
    for trip in trips:
        trip_meta = {
            "trip_id": trip.get("trip_id"),
            "employee_id": trip.get("employee_id"),
            "employee_email": trip.get("employee_email"),
            "trip_name": trip.get("trip_name"),
            "trip_start_date": trip.get("start_date"),
            "trip_end_date": trip.get("end_date"),
        }
        for seg in trip.get("segments", []):
            seg_with_trip = dict(seg)
            seg_with_trip["_trip"] = trip_meta
            segments.append(seg_with_trip)

    # Pre-pass: codeshare duplicate detection by (departure_dt, origin, destination, distance)
    flight_seen: dict[tuple, int] = {}
    for idx, seg in enumerate(segments):
        if seg.get("segment_type") != "flight":
            continue
        key = (
            safe_str(seg.get("departure_datetime")),
            safe_str(seg.get("origin")).upper(),
            safe_str(seg.get("destination")).upper(),
            int(float(seg.get("distance_km") or 0)),
        )
        if not all(key[:3]):
            continue
        flight_seen.setdefault(key, idx)

    for idx, seg in enumerate(segments):
        result.rows.append(_process_segment(seg, ctx, idx, flight_seen))

    return result


def _process_segment(
    seg: dict,
    ctx: LookupContext,
    idx: int,
    flight_seen: dict,
) -> AdapterRowResult:
    trip_meta = seg.get("_trip", {})
    raw_payload = {**seg}
    seg_type = safe_str(seg.get("segment_type")).lower()
    status = safe_str(seg.get("booking_status")).lower()
    vendor = safe_str(seg.get("vendor"))
    currency = safe_str(seg.get("currency")).upper() or None
    amount = parse_decimal(seg.get("amount"))
    confirmation = safe_str(seg.get("confirmation_number")) or None
    ticket_number = safe_str(seg.get("ticket_number")) or None
    leg_id = safe_str(seg.get("leg_id")) or None

    # Exclusion: cancelled/refunded/voided
    if status in EXCLUDED_STATUSES:
        reason = f"{status}_booking" if not status.endswith("_booking") else status
        return AdapterRowResult(
            raw_payload=raw_payload, parse_status="EXCLUDED",
            eligibility_status="EXCLUDED", exclusion_reason=reason,
        )

    # Expense-only segment with no useful basis
    if seg_type == "expense":
        return AdapterRowResult(
            raw_payload=raw_payload, parse_status="EXCLUDED",
            eligibility_status="NOT_RELEVANT",
            exclusion_reason="expense_only_no_travel_segment",
        )

    # Dispatch by segment type
    if seg_type == "flight":
        return _process_flight(seg, trip_meta, ctx, idx, flight_seen,
                               raw_payload, vendor, currency, amount, confirmation,
                               ticket_number, leg_id)
    if seg_type == "hotel":
        return _process_hotel(seg, trip_meta, ctx, raw_payload, vendor,
                              currency, amount, confirmation)
    if seg_type in ("car_rental", "car"):
        return _process_car(seg, trip_meta, ctx, raw_payload, vendor,
                            currency, amount, confirmation, seg_type)
    if seg_type == "rail":
        return _process_rail(seg, trip_meta, ctx, raw_payload, vendor,
                             currency, amount, confirmation, leg_id)
    if seg_type in ("rideshare", "taxi"):
        return _process_rideshare(seg, trip_meta, ctx, raw_payload, vendor,
                                  currency, amount, confirmation, seg_type)

    # Unknown segment type
    a = _new_travel_draft(vendor, currency, amount, confirmation, trip_meta)
    a.activity_type = "travel_other"
    a.eligibility_status = "NEEDS_REVIEW"
    a.add_issue("UNKNOWN_TRAVEL_CATEGORY", severity="WARNING",
                message=f"Segment type '{seg_type}' not recognized")
    _finalize(a, ctx)
    return AdapterRowResult(raw_payload=raw_payload, parse_status="PARSED",
                            eligibility_status="NEEDS_REVIEW", activities=[a])


# -------- per-segment-type processors --------

def _process_flight(seg, trip_meta, ctx, idx, flight_seen, raw_payload,
                    vendor, currency, amount, confirmation, ticket_number, leg_id):
    a = _new_travel_draft(vendor, currency, amount, confirmation, trip_meta)
    a.activity_type = "flight"
    a.calculation_method = "distance_based"
    a.emission_method = "distance_based"
    a.activity_basis = "completed_travel"
    a.scope = 3
    a.scope_category = "3.6 business travel"
    a.source_of_truth = "flown_ticket"
    a.source_hierarchy_rank = 1
    a.reference_id = ticket_number or confirmation

    origin = safe_str(seg.get("origin")).upper() or None
    destination = safe_str(seg.get("destination")).upper() or None
    a.origin = origin
    a.destination = destination

    # Distance resolution
    distance = parse_decimal(seg.get("distance_km"))
    if distance is None or distance <= 0:
        if origin and destination and origin in ctx.airports and destination in ctx.airports:
            o = ctx.airports[origin]
            d = ctx.airports[destination]
            try:
                km = Decimal(str(round(haversine_km(float(o.latitude), float(o.longitude),
                                                    float(d.latitude), float(d.longitude)), 1)))
                distance = km
                a.add_issue("DISTANCE_ESTIMATED", severity="INFO",
                            message=f"Distance estimated via haversine: {km} km")
                a.set_provenance(
                    "distance_km", method="RULE_BASED",
                    rule=f"Haversine:{origin}->{destination}",
                    confidence=0.93, note="Great-circle; actual routing differs",
                )
            except (TypeError, ValueError):
                distance = None
        if distance is None:
            a.add_issue("MISSING_FLIGHT_DISTANCE", severity="ERROR",
                        message="Distance missing and cannot be inferred from airport codes")
            a.eligibility_status = "NEEDS_REVIEW"
            if not (origin and destination):
                a.add_issue("MISSING_ORIGIN_DESTINATION", severity="ERROR",
                            message="Origin/destination IATA codes missing")

    # Cabin class mapping
    cabin_code = safe_str(seg.get("cabin_class")) or None
    cabin_label, unknown_cabin = normalization.cabin_label(cabin_code, default="economy")
    if cabin_code is None or cabin_code == "":
        a.add_issue("CABIN_CLASS_MISSING", severity="WARNING",
                    message="Cabin class missing — defaulted to economy")
    elif unknown_cabin:
        a.add_issue("UNKNOWN_CABIN_CLASS", severity="WARNING",
                    message=f"Cabin code '{cabin_code}' not recognized — defaulted to economy")

    a.activity_subtype = normalization.classify_flight_subtype(distance, cabin_label)
    a.set_provenance("activity_subtype", method="RULE_BASED",
                     rule=f"CabinClass:{cabin_code}->{cabin_label};distance={distance or 0}",
                     confidence=0.9 if not unknown_cabin else 0.7)

    # Codeshare dup detection
    key = (
        safe_str(seg.get("departure_datetime")),
        origin or "",
        destination or "",
        int(float(distance or 0)),
    )
    first_idx = flight_seen.get(key)
    if first_idx is not None and first_idx != idx:
        a.add_issue("POSSIBLE_CODESHARE_DUPLICATE", severity="WARNING",
                    message=f"Possible codeshare duplicate of segment row {first_idx + 1}")
        a.is_duplicate = True

    # Package detection
    if seg.get("package_bundle_id"):
        a.add_issue("BUNDLED_TRAVEL_PACKAGE", severity="WARNING",
                    message=f"Part of bundled package {seg.get('package_bundle_id')}")

    # Persist canonical fields
    a.activity_date = parse_date(safe_str(seg.get("departure_datetime"))[:10] or trip_meta.get("trip_start_date"))
    a.quantity = distance
    a.unit = "km" if distance else None
    a.normalized_quantity = distance
    a.normalized_unit = "km" if distance else None
    a.event_key = f"travel:flight:{ticket_number or confirmation or ''}:{key[0]}"
    if leg_id:
        a.parent_event_key = f"travel:leg:{leg_id}"

    _finalize(a, ctx)
    return AdapterRowResult(raw_payload=raw_payload, parse_status="PARSED",
                            eligibility_status=a.eligibility_status, activities=[a])


def _process_hotel(seg, trip_meta, ctx, raw_payload, vendor, currency, amount, confirmation):
    a = _new_travel_draft(vendor, currency, amount, confirmation, trip_meta)
    a.activity_type = "hotel"
    a.activity_subtype = "standard"
    a.scope = 3
    a.scope_category = "3.6 business travel"
    a.source_of_truth = "stayed_room_nights"
    a.source_hierarchy_rank = 1

    check_in = parse_date(seg.get("check_in_date"))
    check_out = parse_date(seg.get("check_out_date"))
    room_count = int(seg.get("room_count") or 1)
    city = safe_str(seg.get("city"))
    country = safe_str(seg.get("country"))
    a.facility_name = city or None
    a.facility_country = country or None
    a.activity_date = check_in

    if check_out is None:
        a.add_issue("MISSING_CHECKOUT", severity="ERROR",
                    message="Hotel check-out missing — room-nights cannot be computed")
        a.eligibility_status = "NEEDS_REVIEW"
        a.calculation_method = "room_night_based"
        a.emission_method = "room_night_based"
        _finalize(a, ctx)
        return AdapterRowResult(raw_payload=raw_payload, parse_status="PARSED",
                                eligibility_status="NEEDS_REVIEW", activities=[a])

    nights = (check_out - check_in).days * room_count if check_in else 0
    if check_in and check_out and check_in == check_out:
        a.add_issue("ZERO_ROOM_NIGHTS", severity="WARNING",
                    message="Check-in equals check-out")
        a.eligibility_status = "NEEDS_REVIEW"

    a.period_start = check_in
    a.period_end = check_out
    a.quantity = Decimal(nights) if nights > 0 else None
    a.unit = "room-night"
    a.normalized_quantity = a.quantity
    a.normalized_unit = "room-night"
    a.activity_basis = "stayed_room_nights"
    a.calculation_method = "room_night_based"
    a.emission_method = "room_night_based"

    if not city:
        a.add_issue("HOTEL_LOCATION_MISSING", severity="WARNING",
                    message="Hotel city missing")

    if seg.get("package_bundle_id"):
        a.add_issue("BUNDLED_TRAVEL_PACKAGE", severity="WARNING",
                    message=f"Part of bundled package {seg.get('package_bundle_id')}")
        # Bundled hotels can't be reliably room-night counted without itemization
        a.eligibility_status = "NEEDS_REVIEW"

    a.event_key = f"travel:hotel:{confirmation or ''}:{check_in.isoformat() if check_in else '-'}"
    _finalize(a, ctx)
    return AdapterRowResult(raw_payload=raw_payload, parse_status="PARSED",
                            eligibility_status=a.eligibility_status, activities=[a])


def _process_car(seg, trip_meta, ctx, raw_payload, vendor, currency, amount, confirmation, seg_type):
    a = _new_travel_draft(vendor, currency, amount, confirmation, trip_meta)
    a.activity_type = "car_rental"
    a.activity_subtype = "gasoline"
    a.scope = 3
    a.scope_category = "3.6 business travel"
    pickup_city = safe_str(seg.get("pickup_city"))
    dropoff_city = safe_str(seg.get("dropoff_city"))
    distance = parse_decimal(seg.get("distance_km"))
    fuel_l = parse_decimal(seg.get("fuel_litres"))
    a.origin = pickup_city or None
    a.destination = dropoff_city or None
    a.activity_date = parse_date(seg.get("pickup_datetime")) or parse_date(trip_meta.get("trip_start_date"))

    if fuel_l is not None and fuel_l > 0:
        a.calculation_method = "fuel_based"
        a.emission_method = "fuel_based"
        a.activity_basis = "actual_consumption"
        a.quantity = fuel_l
        a.unit = "L"
        a.source_hierarchy_rank = 1
    elif distance is not None and distance > 0:
        a.calculation_method = "distance_based"
        a.emission_method = "distance_based"
        a.activity_basis = "distance_estimated" if distance < 50 else "completed_travel"
        a.quantity = distance
        a.unit = "km"
        a.normalized_quantity = distance
        a.normalized_unit = "km"
        a.source_hierarchy_rank = 2
        if pickup_city and dropoff_city and pickup_city.lower() == dropoff_city.lower():
            a.add_issue("RENTAL_CAR_DOUBLE_COUNT_RISK", severity="WARNING",
                        message="Same city pickup/dropoff — risk of double-count with fuel receipts")
    else:
        a.calculation_method = "spend_based"
        a.emission_method = "spend_based"
        a.activity_basis = "spend_only"
        a.activity_subtype = "general"
        a.source_hierarchy_rank = 4
        a.add_issue("SPEND_BASED_FALLBACK", severity="INFO",
                    message="No distance or fuel — spend-based")
        if pickup_city and dropoff_city and pickup_city.lower() == dropoff_city.lower():
            a.add_issue("RENTAL_CAR_DOUBLE_COUNT_RISK", severity="WARNING",
                        message="Same city pickup/dropoff")

    a.event_key = f"travel:car:{confirmation or ''}"
    _finalize(a, ctx)
    return AdapterRowResult(raw_payload=raw_payload, parse_status="PARSED",
                            eligibility_status=a.eligibility_status, activities=[a])


def _process_rail(seg, trip_meta, ctx, raw_payload, vendor, currency, amount, confirmation, leg_id):
    a = _new_travel_draft(vendor, currency, amount, confirmation, trip_meta)
    a.activity_type = "rail"
    a.activity_subtype = "intercity"
    a.calculation_method = "distance_based"
    a.emission_method = "distance_based"
    a.activity_basis = "completed_travel"
    a.scope = 3
    a.scope_category = "3.6 business travel"
    origin_city = safe_str(seg.get("origin_city"))
    destination_city = safe_str(seg.get("destination_city"))
    a.origin = origin_city or None
    a.destination = destination_city or None
    distance = parse_decimal(seg.get("distance_km"))
    if distance is None:
        # Try city-code haversine
        o = ctx.city_codes.get(origin_city.upper()[:3]) if origin_city else None
        d = ctx.city_codes.get(destination_city.upper()[:3]) if destination_city else None
        if o and d:
            distance = Decimal(str(round(haversine_km(float(o.latitude), float(o.longitude),
                                                       float(d.latitude), float(d.longitude)), 1)))
            a.add_issue("RAIL_DISTANCE_ESTIMATED", severity="INFO",
                        message="Distance estimated via city haversine")
    if distance is None:
        a.add_issue("MISSING_FLIGHT_DISTANCE", severity="ERROR",
                    message="Rail distance missing and cannot be inferred")
        a.eligibility_status = "NEEDS_REVIEW"
    else:
        a.quantity = distance
        a.unit = "km"
        a.normalized_quantity = distance
        a.normalized_unit = "km"
    a.activity_date = parse_date(trip_meta.get("trip_start_date"))
    a.event_key = f"travel:rail:{confirmation or ''}:{leg_id or ''}"
    _finalize(a, ctx)
    return AdapterRowResult(raw_payload=raw_payload, parse_status="PARSED",
                            eligibility_status=a.eligibility_status, activities=[a])


def _process_rideshare(seg, trip_meta, ctx, raw_payload, vendor, currency, amount,
                       confirmation, seg_type):
    a = _new_travel_draft(vendor, currency, amount, confirmation, trip_meta)
    a.activity_type = seg_type
    a.activity_subtype = "gasoline"
    a.scope = 3
    a.scope_category = "3.6 business travel"
    a.activity_date = parse_date(trip_meta.get("trip_start_date"))
    distance = parse_decimal(seg.get("distance_km"))
    if distance is not None and distance > 0:
        a.calculation_method = "distance_based"
        a.emission_method = "distance_based"
        a.activity_basis = "completed_travel"
        a.quantity = distance
        a.unit = "km"
        a.normalized_quantity = distance
        a.normalized_unit = "km"
        a.source_hierarchy_rank = 2
    else:
        a.calculation_method = "spend_based"
        a.emission_method = "spend_based"
        a.activity_subtype = "general"
        a.activity_basis = "spend_only"
        a.add_issue("AMOUNT_ONLY_TRAVEL_ROW", severity="INFO",
                    message="Amount only — spend-based, capped at LOW confidence")
        a.add_issue("SPEND_BASED_FALLBACK", severity="INFO",
                    message="No distance — spend-based")
        a.source_hierarchy_rank = 4
    a.event_key = f"travel:{seg_type}:{confirmation or ''}"
    _finalize(a, ctx)
    return AdapterRowResult(raw_payload=raw_payload, parse_status="PARSED",
                            eligibility_status=a.eligibility_status, activities=[a])


# -------- shared helpers --------

def _new_travel_draft(vendor, currency, amount, confirmation, trip_meta) -> ActivityDraft:
    a = ActivityDraft(source_type="travel")
    a.vendor = vendor or None
    a.currency = currency
    a.amount = amount
    a.reference_id = confirmation
    a.set_provenance("activity_type", method="DIRECT", source_field="segment_type", confidence=1.0)
    return a


def _finalize(activity: ActivityDraft, ctx: LookupContext) -> None:
    if activity.normalized_quantity is None and activity.quantity is not None:
        if activity.unit and activity.unit != "km":
            normalization.normalize_unit(activity, ctx)
        else:
            activity.normalized_quantity = activity.quantity
            activity.normalized_unit = activity.unit
    normalization.apply_emission_factor(activity, ctx, region=activity.facility_country)
    confidence_service.apply(activity)
