# Breathe ESG — Data Model

The model is shaped around one principle: **raw data is permanent, decisions are explicit, uncertainty is visible**. That means every source row is kept, every transformation has a recorded reason, and every score can be traced back to a flag.

This document walks each model, what it stores, and the design choice behind it. The full field set is in [`backend/`](backend/) — I'm only highlighting the parts that are not obvious from the column list.

---

## Tenant — multi-tenancy boundary

```python
class Tenant: id, name, slug, created_at
```

Every domain model holds a `tenant` foreign key; every query is tenant-scoped. The prototype seeds one tenant ("Demo Enterprise Client") but the schema is already multi-tenant.

**Why this exists in the prototype:**
A row from one client must never appear in another client's dashboard, including in lookup tables that may carry client-specific facility codes. Building tenant scoping into the schema now means deploying multi-tenant later is a config change, not a refactor.

---

## IngestionBatch — the unit of work

One batch per upload or travel sync. The batch row stores:

- `source_type`, `ingestion_method`, `original_filename` or `api_sync_range_start/end`, `status`.
- Funnel counts at every pipeline stage: `total_rows`, `raw_rows_stored`, `eligible_rows`, `excluded_rows`, `not_relevant_rows`, `failed_rows`, `flagged_rows`, `suspicious_rows`, `low_confidence_rows`, `llm_suggested_rows`, `pending_rows`, `approved_rows`, `rejected_rows`, `locked_rows`.
- **Lookup versions in effect at ingestion**: `plant_lookup_version`, `material_lookup_version`, `unit_mapping_version`, `meter_mapping_version`, `ef_version`.

**Why the lookup-version snapshot matters:**
If a customer adds a plant code six weeks after an ingest, or an emission factor is bumped, I still need to be able to answer "what was this batch based on?" Storing the versions at ingestion time makes that reconstructible without time-travelling the lookups.

---

## RawRecord — preserve the original row, always

```python
class RawRecord:
    raw_payload (JSONField),    # source row verbatim
    parse_status,               # PARSED | FAILED | EXCLUDED
    eligibility_status,         # set after eligibility filter
    exclusion_reason,           # structured reason; see below
    error_message
```

Every source row is stored — including the ones I deliberately skip. The exclusion_reason values are structured, not free text:

- `movement_type_101_receipt`, `movement_type_311_transfer` (SAP)
- `cancelled_booking`, `refunded_booking`, `voided_booking`, `expense_only_no_travel_segment` (travel)
- `tax_only_utility_row`, `late_fee_only_row`, `gas_row_rejected_from_electricity` (utility)

**Why I keep excluded rows:**
If an analyst challenges a decision, I point at the raw row. If I find an adapter bug six weeks later, I reprocess from raw without re-asking the customer for the file. Discarding excluded rows would erase the system's ability to defend itself.

---

## NormalizedActivity — the operational ESG model

This is the model the analyst dashboard reads from. Eligible source rows produce one or more `NormalizedActivity` rows (utility bills can fan out into multiple per-month rows via pro-rata).

The full field set is in [`backend/activities/models.py`](backend/activities/models.py). The non-obvious parts:

### Quantity stored twice — raw and normalized

```
quantity + unit             ← exactly as it appeared in source
normalized_quantity + unit  ← after UnitMapping conversion
```

**Why both:** the raw pair is for audit; the normalized pair is what the emission factor multiplies against. Unit-conversion bugs are easy to spot when both are visible side by side.

### Classification, eligibility, and method as separate fields

- `activity_type`, `activity_subtype`, `scope`, `scope_category` — what the activity is.
- `eligibility_status` — `ELIGIBLE | NOT_RELEVANT | NEEDS_REVIEW | FAILED | EXCLUDED`.
- `source_hierarchy_rank`, `source_of_truth` — which source produced this record and where it sits in the trust hierarchy (1 = best, n = worst).
- `activity_basis`, `calculation_method`, `emission_method` — the method choice, which the UI uses to badge rows (spend-based → amber).

**Why these are separate fields, not derived:**
The analyst sees *why* this row is what it is. If a flight fell through to spend-based, it's stored on the row, not inferred from missing data. That's what makes it explainable.

### Pro-rata via `calendar_month`

Utility bills produce one `NormalizedActivity` per overlapping calendar month, each carrying `calendar_month`, `period_start`, `period_end`, `billing_days`, `usage_per_day`. `usage_per_day` makes spike detection compare like-for-like across different billing-period lengths.

### Dedup and reversal flags

`is_duplicate`, `is_reversal`, `reversal_of`, `is_estimate`, `estimate_reason`, `requires_reconciliation`. Rows stay in the table even when flagged — these booleans drive filtered dashboard views and prevent naive summing.

### Quality fields

- `data_quality_score` (0–100), `confidence_level` (HIGH/MEDIUM/LOW/FAILED).
- `flags` (JSON list of flag codes — fast to filter).
- `field_provenance` (JSON map per field — see below).
- `llm_suggestions` (current unreviewed Groq suggestions), `llm_suggestion_reviewed`.

### Review and lock

`review_status`, `reviewed_by`, `reviewed_at`, `review_comment`, `approved_by`, `approved_at`, `locked_at`, `locked_snapshot`. Approval and lock are separate timestamps (and separate API actions); the lock snapshot freezes provenance and EF version at lock time.

---

## ValidationIssue — the queryable journal

```python
class ValidationIssue: activity, issue_code, severity (ERROR/WARNING/INFO), message
```

`flags` lives on `NormalizedActivity` for fast filtering ("show me everything flagged SUSPICIOUS_HIGH_QUANTITY"). `ValidationIssue` lives in its own table for the analyst's per-row drill-down view and for cross-batch queries ("show me every USAGE_SPIKE this quarter").

**Why both exist:**
Filtering by flag code on the activity list is a hot path — embedding the list on the row keeps that query fast. The full message + severity + timestamp belongs in a journal table I can join on demand, not on every row's read path.

---

## ReviewLog — append-only audit trail

```python
class ReviewLog: activity, action, reviewer, comment, old_value, new_value
```

`action` covers `APPROVED`, `REJECTED`, `FLAGGED`, `MARKED_NOT_RELEVANT`, `CLARIFICATION_REQUESTED`, `LOCKED`, `UNLOCK_REQUESTED`, `LLM_SUGGESTION_ACCEPTED`, `LLM_SUGGESTION_REJECTED`, `VALUE_OVERRIDDEN`.

Every state change writes a row with before/after JSON. Combined with the locked snapshot, the record's history is reconstructible even if downstream lookups or factor versions drift later.

---

## Lookup tables — deterministic enrichment

I'm keeping lookups in the database, not hardcoded in adapter code. The list:

- **Tenant-scoped:** `PlantLookup`, `MaterialLookup`, `UnitMapping`, `CostCenterLookup`, `MeterFacilityLookup`, `TravelCategoryMapping`.
- **Global:** `MovementTypeMapping`, `AirportLookup`, `CityCodeLookup`, `EmissionFactorMapping`.

**Why MovementTypeMapping is global:**
SAP movement type semantics are defined by SAP. `311` means storage-location transfer regardless of which customer is running the system. A customer-custom movement type would override, but the defaults shouldn't be re-keyed per tenant.

**Why lookups are tables and not code:**
Lookups change without code deploys. A new plant code, a new meter at a site, a new emission factor version — all need to be editable by ops without a release. Hardcoding them in adapter code would freeze the model to a single point-in-time view of the world.

---

## Field-level provenance

For every key normalized field, `NormalizedActivity.field_provenance` stores how that value was derived:

```json
{
  "quantity":        { "method": "DIRECT",    "source_field": "Menge",            "confidence": 1.0 },
  "normalized_unit": { "method": "RULE_BASED","rule": "UnitMapping:L->litres",   "confidence": 1.0 },
  "facility_name":   { "method": "RULE_BASED","rule": "PlantLookup:1000->Hamburg","confidence": 0.95 },
  "distance_km":     { "method": "RULE_BASED","rule": "Haversine:LHR->JFK",      "confidence": 0.93,
                       "note": "great-circle; actual routing differs" },
  "activity_subtype":{ "method": "LLM_SUGGESTED","confidence": 0.72,
                       "reason": "Material description contains HSD and genset fuel; mapped to diesel" },
  "facility_name?":  { "method": "MISSING",   "reason": "Plant DE03 not in lookup" }
}
```

Trust hierarchy: `DIRECT > RULE_BASED > ANALYST_OVERRIDDEN > LLM_SUGGESTED > MISSING`.

**Why provenance is a field on the row, not a log table:**
The dashboard needs it inline in the row detail view. The audit lock snapshots it. Provenance is a property of the record, not an event in its history.

**How accepting an LLM suggestion changes provenance:**
Accepting flips `LLM_SUGGESTED` → `ANALYST_OVERRIDDEN`. A locked row can never carry an unreviewed `LLM_SUGGESTED` field — the lock endpoint refuses.

---

## Confidence scoring

`services/confidence.py` starts every row at the method's ceiling (100 for fuel_based, 60 for spend_based, etc.) and subtracts a fixed amount per flag. The score bands into HIGH (80+) / MEDIUM (50–79) / LOW (30–49, LLM-eligible) / FAILED (<30).

**Why a number and bands, not just flags:**
- The dashboard sorts by quality to focus analyst attention.
- The audit lock can be gated on a minimum threshold.
- Quality trend over time is a KPI the customer wants.
- Bands are the unit the analyst thinks in; the number is what the system thinks in.

**Why fixed deductions, not learned weights:**
Every score has to be reconstructible from `flags` alone. An ML score is more accurate in theory but unexplainable; explainability is the whole point of analyst review.

---

## Audit lock

Approval and lock are distinct API actions. `approved_at` records the analyst's sign-off; `locked_at` records immutability. The lock writes `locked_snapshot`:

```json
{
  "field_provenance": { ... },
  "flags": [ ... ],
  "eligibility_status": "ELIGIBLE",
  "source_hierarchy_rank": 1,
  "source_of_truth": "goods_issue",
  "data_quality_score": 92,
  "confidence_level": "HIGH",
  "emission_factor": "2.68",
  "emission_factor_source": "DEFRA 2024 (illustrative) (2024)",
  "co2e_kg": "13400.0",
  "issues": ["GERMAN_HEADER_MAPPING_USED"]
}
```

The API rejects any mutation on a locked row. Unlock requires admin reason (the prototype implements only the rejection path; the admin self-service flow is a production concern).

**Why approve ≠ lock:**
Approval is "I checked this." Lock is "this is the record we'd stand behind in an audit." Some analyst workflows approve a row but don't lock it yet — waiting for a related row, or for a quarterly review. Conflating the two would force a single-step workflow on a multi-step process.
