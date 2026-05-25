"""SAP MB51 / ME2M adapter.

Takes parsed CSV rows (list of dict) and produces AdapterBatchResult with
RawRecord disposition + zero-or-more NormalizedActivity drafts per row.

Key responsibilities:
  - Detect English/German headers, normalize to a canonical key set.
  - Filter rows by SAP movement type (consumption vs purchase vs transfer vs reversal vs scrap).
  - Resolve plant / material / cost-center / unit via lookups.
  - Detect duplicates (same Belegnummer in batch).
  - Emit validation issues and field provenance.
  - Apply emission factor where possible.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..services import confidence as confidence_service
from ..services import normalization
from ..services.drafts import ActivityDraft, AdapterBatchResult, AdapterRowResult
from ..services.lookup_context import LookupContext
from ..services.utils import parse_date, parse_decimal, safe_str


# -------- Header mapping (German/English -> canonical) --------

GERMAN_HEADER_MAP = {
    "buchungsdatum": "posting_date",
    "werk": "plant_code",
    "materialnummer": "material_code",
    "materialkurztext": "material_description",
    "menge": "quantity",
    "me": "unit",
    "basismengeneinheit": "unit",
    "bewegungsart": "movement_type",
    "belegnummer": "document_number",
    "kostenstelle": "cost_center",
    "lagerort": "storage_location",
    "lieferant": "vendor",
    "nettowert": "net_value",
    "waehrung": "currency",
    "währung": "currency",
}

ENGLISH_HEADER_MAP = {
    "posting date": "posting_date",
    "plant": "plant_code",
    "material": "material_code",
    "material description": "material_description",
    "quantity": "quantity",
    "unit": "unit",
    "unit of measure": "unit",
    "base unit of measure": "unit",
    "movement type": "movement_type",
    "document number": "document_number",
    "cost center": "cost_center",
    "storage location": "storage_location",
    "vendor": "vendor",
    "supplier": "vendor",
    "net value": "net_value",
    "currency": "currency",
}


def canonicalize_row(row: dict, header_lang: str) -> dict:
    """Translate a raw row's keys to canonical names; preserves unknown keys."""
    mapping = GERMAN_HEADER_MAP if header_lang == "GERMAN" else ENGLISH_HEADER_MAP
    out: dict = {}
    for k, v in row.items():
        key_lower = (k or "").strip().lower()
        canon = mapping.get(key_lower)
        if canon:
            out[canon] = v
        else:
            out.setdefault(key_lower, v)
    return out


def detect_header_language(headers: list[str]) -> str:
    """Return 'GERMAN' or 'ENGLISH' based on column names."""
    lower = {(h or "").strip().lower() for h in headers}
    german_hits = sum(1 for k in GERMAN_HEADER_MAP if k in lower)
    english_hits = sum(1 for k in ENGLISH_HEADER_MAP if k in lower)
    return "GERMAN" if german_hits > english_hits else "ENGLISH"


# -------- Suspicion thresholds --------

SUSPICIOUS_LITRES = Decimal("30000")
SUSPICIOUS_M3 = Decimal("30000")
SUSPICIOUS_KG = Decimal("30000")


# -------- Main entry --------

def adapt_mb51(
    rows: list[dict],
    ctx: LookupContext,
    *,
    source_label: str = "sap",
) -> AdapterBatchResult:
    """Process MB51-style fuel movement rows."""
    headers = list(rows[0].keys()) if rows else []
    header_lang = detect_header_language(headers)
    result = AdapterBatchResult(metadata={"header_language": header_lang, "source": "sap_mb51"})

    seen_docs: dict[str, int] = {}  # document_number -> first-seen row index
    for idx, raw in enumerate(rows):
        canon = canonicalize_row(raw, header_lang)
        result.rows.append(_process_mb51_row(raw, canon, ctx, idx, seen_docs, header_lang))

    return result


def adapt_me2m(
    rows: list[dict],
    ctx: LookupContext,
    *,
    source_label: str = "sap",
) -> AdapterBatchResult:
    """Process ME2M-style procurement rows.

    Procurement rows are treated as fuel_purchased (when material is fuel and unit is energy)
    or fall to spend_based when unit is non-energy (RM, ST, BOX, EACH).
    """
    headers = list(rows[0].keys()) if rows else []
    header_lang = detect_header_language(headers)
    result = AdapterBatchResult(metadata={"header_language": header_lang, "source": "sap_me2m"})

    seen_docs: dict[str, int] = {}
    for idx, raw in enumerate(rows):
        canon = canonicalize_row(raw, header_lang)
        result.rows.append(_process_me2m_row(raw, canon, ctx, idx, seen_docs, header_lang))

    return result


# -------- Row processors --------

def _process_mb51_row(
    raw: dict,
    canon: dict,
    ctx: LookupContext,
    idx: int,
    seen_docs: dict[str, int],
    header_lang: str,
) -> AdapterRowResult:
    movement_type = safe_str(canon.get("movement_type"))
    plant_code = safe_str(canon.get("plant_code")).upper()
    material_code = safe_str(canon.get("material_code")).upper()
    material_desc = safe_str(canon.get("material_description"))
    document_number = safe_str(canon.get("document_number"))
    posting_date_str = safe_str(canon.get("posting_date"))
    quantity_raw = canon.get("quantity")
    unit_raw = safe_str(canon.get("unit")).upper()
    cost_center_code = safe_str(canon.get("cost_center")).upper()
    vendor = safe_str(canon.get("vendor"))

    posting_date = parse_date(posting_date_str)
    quantity = parse_decimal(quantity_raw)

    # Look up movement-type semantics.
    mt = ctx.movement_types.get(movement_type)

    # Exclusion paths — no NormalizedActivity created.
    if mt is None:
        # Unknown movement type → still create an activity for analyst review.
        activity = _new_consumption_draft(
            ctx, posting_date, plant_code, material_code, material_desc,
            quantity, unit_raw, document_number, cost_center_code, vendor,
            header_lang,
        )
        activity.eligibility_status = "NEEDS_REVIEW"
        activity.add_issue("UNSUPPORTED_MOVEMENT_TYPE", severity="WARNING",
                           message=f"Movement type {movement_type or '(blank)'} not mapped")
        _finalize_activity(activity, ctx)
        return AdapterRowResult(
            raw_payload=raw, parse_status="PARSED",
            eligibility_status="NEEDS_REVIEW", activities=[activity],
        )

    if mt.esg_relevance == "TRANSFER":
        return AdapterRowResult(
            raw_payload=raw, parse_status="EXCLUDED",
            eligibility_status="EXCLUDED",
            exclusion_reason=f"movement_type_{movement_type}_transfer",
        )
    if mt.esg_relevance == "ADJUSTMENT" and mt.default_action == "IGNORE_NON_RELEVANT":
        return AdapterRowResult(
            raw_payload=raw, parse_status="EXCLUDED",
            eligibility_status="NOT_RELEVANT",
            exclusion_reason=f"movement_type_{movement_type}_adjustment",
        )

    # Build an activity draft for all remaining cases.
    activity = _new_consumption_draft(
        ctx, posting_date, plant_code, material_code, material_desc,
        quantity, unit_raw, document_number, cost_center_code, vendor,
        header_lang,
    )

    if mt.esg_relevance == "PURCHASE":
        activity.activity_type = "fuel_purchased"
        activity.activity_basis = "purchase"
        activity.calculation_method = "fuel_based"
        activity.emission_method = "fuel_based"
        activity.scope = 1
        activity.scope_category = "1.1 stationary combustion (purchased)"
        activity.source_of_truth = "purchase_invoice"
        activity.source_hierarchy_rank = 3
        activity.add_issue("PURCHASE_NOT_CONSUMPTION", severity="INFO",
                           message="Goods receipt — fuel arrived but not yet burned")
        # Purchased fuel is not Scope 1 emissions; downstream summing should exclude these
        # unless analyst flags it as a fallback. Keep eligibility as NEEDS_REVIEW.
        activity.eligibility_status = "NEEDS_REVIEW"
    elif mt.esg_relevance == "REVERSAL":
        activity.activity_type = "fuel_consumed"
        activity.activity_basis = "reversal"
        activity.calculation_method = "fuel_based"
        activity.emission_method = "fuel_based"
        activity.scope = 1
        activity.is_reversal = True
        activity.reversal_of = document_number  # heuristic — in practice would link to original
        activity.add_issue("REVERSAL_ROW", severity="INFO",
                           message=f"Reversal row (mt={movement_type})")
        if quantity is not None and quantity > 0:
            activity.quantity = -quantity  # net negative
    elif mt.esg_relevance == "SCRAP":
        activity.activity_type = "fuel_consumed"
        activity.activity_basis = "scrap"
        activity.calculation_method = "fuel_based"
        activity.emission_method = "fuel_based"
        activity.scope = 1
        activity.eligibility_status = "NEEDS_REVIEW"
        activity.add_issue("SCRAP_REQUIRES_REVIEW", severity="INFO",
                           message="Scrapping / write-off — needs analyst confirmation")
    else:  # CONSUMPTION
        activity.activity_type = "fuel_consumed"
        activity.activity_basis = "actual_consumption"
        activity.calculation_method = "fuel_based"
        activity.emission_method = "fuel_based"
        activity.scope = 1
        activity.scope_category = "1.1 stationary combustion"
        activity.source_of_truth = "goods_issue"
        activity.source_hierarchy_rank = 2

    # Quantity sanity flags
    if quantity is None:
        activity.add_issue("MISSING_QUANTITY", severity="ERROR", message="Quantity missing or unparseable")
    elif quantity == 0:
        activity.add_issue("ZERO_QUANTITY", severity="WARNING", message="Quantity is zero")
    elif quantity < 0 and not activity.is_reversal:
        activity.add_issue("NEGATIVE_QUANTITY", severity="WARNING", message="Quantity is negative")
    elif unit_raw == "L" and quantity > SUSPICIOUS_LITRES:
        activity.add_issue("SUSPICIOUS_HIGH_QUANTITY", severity="WARNING",
                           message=f"Quantity {quantity} L is unusually high")
    elif unit_raw == "M3" and quantity > SUSPICIOUS_M3:
        activity.add_issue("SUSPICIOUS_HIGH_QUANTITY", severity="WARNING",
                           message=f"Quantity {quantity} m3 is unusually high")
    elif unit_raw == "KG" and quantity > SUSPICIOUS_KG:
        activity.add_issue("SUSPICIOUS_HIGH_QUANTITY", severity="WARNING",
                           message=f"Quantity {quantity} kg is unusually high")

    if not unit_raw:
        activity.add_issue("MISSING_UNIT", severity="ERROR", message="Unit code missing")
    if posting_date is None:
        activity.add_issue("MISSING_POSTING_DATE", severity="ERROR", message="Posting date missing or unparseable")

    # Duplicate document detection (within batch)
    if document_number:
        if document_number in seen_docs:
            activity.add_issue("DUPLICATE_DOCUMENT", severity="WARNING",
                               message=f"Document number {document_number} already seen in this batch (row {seen_docs[document_number]+1})")
            activity.is_duplicate = True
        else:
            seen_docs[document_number] = idx

    # Material / fuel subtype resolution
    material = ctx.materials.get(material_code)
    if material is None and material_code:
        activity.add_issue("UNKNOWN_MATERIAL_CODE", severity="WARNING",
                           message=f"Material {material_code} not in lookup")
    if material and material.fuel_type:
        activity.activity_subtype = material.fuel_type
        activity.set_provenance(
            "activity_subtype",
            method="RULE_BASED",
            rule=f"MaterialLookup:{material_code}->{material.fuel_type}",
            confidence=0.95,
        )
    elif material and not material.fuel_type and activity.activity_type == "fuel_consumed":
        # Material exists but isn't a known fuel — flag for review and demote to spend.
        activity.add_issue("UNKNOWN_MATERIAL_GROUP", severity="WARNING",
                           message=f"Material {material_code} ({material.description}) has no fuel_type — not classified as fuel")
        activity.calculation_method = "spend_based"
        activity.emission_method = "spend_based"
        activity.eligibility_status = "NEEDS_REVIEW"

    # KG → density-required for litres-based factor
    if unit_raw == "KG" and material and material.fuel_type in ("diesel", "petrol", "heating_oil"):
        activity.add_issue("UNIT_DENSITY_CONVERSION_REQUIRED", severity="INFO",
                           message="KG unit; factor lookup will use kg directly where available")

    # Header language info flag
    if header_lang == "GERMAN":
        activity.add_issue("GERMAN_HEADER_MAPPING_USED", severity="INFO",
                           message="File detected as German-language header")

    # Event key (for cross-batch dedup later)
    if document_number:
        activity.event_key = f"sap:mb51:{ctx.tenant.slug}:{document_number}"
    if activity.is_reversal:
        activity.parent_event_key = f"sap:mb51:{ctx.tenant.slug}:{document_number}"

    _finalize_activity(activity, ctx)

    # Eligibility downgrade on hard errors
    has_error = any(i.severity == "ERROR" for i in activity.issues)
    if has_error and activity.eligibility_status == "ELIGIBLE":
        activity.eligibility_status = "NEEDS_REVIEW"

    return AdapterRowResult(
        raw_payload=raw, parse_status="PARSED",
        eligibility_status=activity.eligibility_status, activities=[activity],
    )


def _process_me2m_row(
    raw: dict,
    canon: dict,
    ctx: LookupContext,
    idx: int,
    seen_docs: dict[str, int],
    header_lang: str,
) -> AdapterRowResult:
    plant_code = safe_str(canon.get("plant_code")).upper()
    material_code = safe_str(canon.get("material_code")).upper()
    material_desc = safe_str(canon.get("material_description"))
    document_number = safe_str(canon.get("document_number"))
    posting_date = parse_date(safe_str(canon.get("posting_date")))
    quantity = parse_decimal(canon.get("quantity"))
    unit_raw = safe_str(canon.get("unit")).upper()
    cost_center_code = safe_str(canon.get("cost_center")).upper()
    vendor = safe_str(canon.get("vendor"))
    net_value = parse_decimal(canon.get("net_value"))
    currency = safe_str(canon.get("currency")).upper() or None

    activity = _new_consumption_draft(
        ctx, posting_date, plant_code, material_code, material_desc,
        quantity, unit_raw, document_number, cost_center_code, vendor,
        header_lang,
    )
    activity.amount = net_value
    activity.currency = currency
    activity.scope = 3
    activity.scope_category = "3.1 purchased goods & services"
    activity.source_of_truth = "purchase_invoice"
    activity.source_hierarchy_rank = 4

    material = ctx.materials.get(material_code)
    is_fuel = bool(material and material.fuel_type)
    has_energy_unit = unit_raw in {"L", "KG", "M3", "TO", "GAL", "MJ", "KWH", "USG", "LTR", "T", "G"}

    if is_fuel and has_energy_unit:
        activity.activity_type = "fuel_purchased"
        activity.activity_subtype = material.fuel_type
        activity.activity_basis = "purchase"
        activity.calculation_method = "fuel_based"
        activity.emission_method = "fuel_based"
        activity.scope = 1
        activity.scope_category = "1.1 stationary combustion (purchased)"
        activity.eligibility_status = "NEEDS_REVIEW"
        activity.add_issue("PURCHASE_NOT_CONSUMPTION", severity="INFO",
                           message="Procurement record — fuel purchased, not consumption")
    else:
        # Spend-based fallback
        activity.activity_type = "spend_based"
        activity.activity_subtype = "office_supplies" if unit_raw in ("RM", "ST", "BOX", "EACH") else "general"
        activity.activity_basis = "spend_only"
        activity.calculation_method = "spend_based"
        activity.emission_method = "spend_based"
        activity.eligibility_status = "ELIGIBLE"
        activity.add_issue("SPEND_BASED_FALLBACK", severity="INFO",
                           message="Non-energy unit — spend-based method applied")

    if document_number:
        if document_number in seen_docs:
            activity.add_issue("DUPLICATE_DOCUMENT", severity="WARNING",
                               message=f"Document {document_number} duplicate in batch")
            activity.is_duplicate = True
        else:
            seen_docs[document_number] = idx
        activity.event_key = f"sap:me2m:{ctx.tenant.slug}:{document_number}"

    if quantity is None:
        activity.add_issue("MISSING_QUANTITY", severity="ERROR", message="Quantity missing")
    if not unit_raw:
        activity.add_issue("MISSING_UNIT", severity="ERROR", message="Unit code missing")
    if posting_date is None:
        activity.add_issue("MISSING_POSTING_DATE", severity="ERROR", message="Posting date missing")
    if net_value is None and activity.calculation_method == "spend_based":
        activity.add_issue("MISSING_REQUIRED_FIELD", severity="ERROR", message="Net value missing for spend-based row")

    _finalize_activity(activity, ctx)
    return AdapterRowResult(
        raw_payload=raw, parse_status="PARSED",
        eligibility_status=activity.eligibility_status, activities=[activity],
    )


# -------- Shared helpers --------

def _new_consumption_draft(
    ctx: LookupContext,
    posting_date: date | None,
    plant_code: str,
    material_code: str,
    material_desc: str,
    quantity: Decimal | None,
    unit_raw: str,
    document_number: str,
    cost_center_code: str,
    vendor: str,
    header_lang: str,
) -> ActivityDraft:
    a = ActivityDraft(source_type="sap")
    a.activity_date = posting_date
    a.facility_code = plant_code or None
    a.cost_center = cost_center_code or None
    a.reference_id = document_number or None
    a.vendor = vendor or None
    a.quantity = quantity
    a.unit = unit_raw or None
    a.set_provenance("quantity", method="DIRECT" if quantity is not None else "MISSING",
                     source_field=("Menge" if header_lang == "GERMAN" else "Quantity"),
                     confidence=1.0 if quantity is not None else 0.0)
    a.set_provenance("unit", method="DIRECT" if unit_raw else "MISSING",
                     source_field=("ME" if header_lang == "GERMAN" else "Unit"),
                     confidence=1.0 if unit_raw else 0.0)
    a.set_provenance("activity_date", method="DIRECT" if posting_date else "MISSING",
                     source_field=("Buchungsdatum" if header_lang == "GERMAN" else "Posting Date"),
                     confidence=1.0 if posting_date else 0.0)

    # Plant → facility
    plant = ctx.plants.get(plant_code) if plant_code else None
    if plant:
        a.facility_name = plant.facility_name
        a.facility_country = plant.facility_country
        a.set_provenance("facility_name", method="RULE_BASED",
                         rule=f"PlantLookup:{plant_code}->{plant.facility_name}",
                         confidence=0.95)
    else:
        if plant_code:
            a.add_issue("MISSING_FACILITY_MAPPING", severity="WARNING",
                        message=f"Plant {plant_code} not in lookup")
            a.add_issue("UNKNOWN_PLANT_CODE", severity="WARNING",
                        message=f"Plant {plant_code} not in lookup")
        else:
            a.add_issue("MISSING_FACILITY_MAPPING", severity="WARNING",
                        message="Plant code missing")
    return a


def _finalize_activity(activity: ActivityDraft, ctx: LookupContext) -> None:
    """Normalize unit, calculate emissions, score confidence."""
    normalization.normalize_unit(activity, ctx)
    region_hint = activity.facility_country or None
    normalization.apply_emission_factor(activity, ctx, region=region_hint)
    confidence_service.apply(activity)
