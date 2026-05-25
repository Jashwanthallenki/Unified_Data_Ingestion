# Breathe ESG — Approach

This is my end-to-end thinking for the Breathe ESG Tech Intern assignment: how I read the problem, how I split the product, what I chose to build, what I chose to leave out, and why each decision holds up to scrutiny.

The shorter design docs are referenced inline:

- [MODEL.md](MODEL.md) — full data model walkthrough.
- [DECISIONS.md](DECISIONS.md) — 14 numbered decisions with the "why".
- [TRADEOFFS.md](TRADEOFFS.md) — what I deliberately did not build.
- [SOURCES.md](SOURCES.md) — per-source: research, sample data, what would break in production.
- [PLAN.md](PLAN.md) — milestones, what shipped.
- [README.md](README.md) — how to run.

---

## 1. Problem understanding

Breathe ESG ingests emissions and activity data from enterprise clients. When I started, I deliberately reframed the problem before writing any code.

**The hard problem here is not carbon calculation.** The hard problem is that every client's data arrives differently — different source systems, different formats, different field names, missing values, wrong units, duplicate records, cancelled / reversed transactions, suspicious-looking rows, and activity data mixed with accounting data. Carbon math is well-defined once you know what you're multiplying. Knowing what to multiply is the actual job.

That reframing led to a system that doesn't blindly convert every incoming row into an emission record. For every source row, the system asks:

- Is this row ESG-relevant at all?
- Is it actual activity, or only an accounting / payment / inventory record?
- Is it duplicated, reversed, cancelled, estimated, or incomplete?
- Can it be normalized safely (unit known, period valid, facility resolved)?
- What confidence level can I attach to it?
- Does an analyst need to review it before it counts?

If I answered "no" or "I don't know" to any of those, the row had to be preserved and surfaced, not silently converted into a number that downstream reports would trust.

---

## 2. Product architecture — two connected systems

I split the product into two systems that share one backend and one normalized model:

### System 1 — Ingestion Console (`/ingestion`)

The operational entry point for onboarding and data-ops users. It handles:

- SAP CSV / Excel upload (MB51-like fuel movements and ME2M-like procurement).
- Utility CSV upload (utility-portal / Green Button-style exports).
- Mock travel API sync (Concur / Navan-shaped).
- Raw record storage for every source row, including excluded ones.
- Source-specific parsing (German / English headers, EU / US numeric formats).
- Eligibility filtering (movement-type filter, charge-type filter, cancellation filter).
- Exclusion logging with structured reasons.
- Validation and confidence scoring.
- Batch-level status and funnel counts.

This is where messy data enters and gets stamped with its identity, eligibility, and quality.

### System 2 — Analyst Review Dashboard (`/review`)

The analyst-facing layer. It handles:

- Filtered views of normalized activities (by source, confidence, eligibility, status, flag).
- Suspicious-row and low-confidence-row queues.
- Field-level provenance — for every key field, how it was derived.
- Validation issues per record, with severity.
- Optional Groq LLM suggestions for low-confidence rows.
- Approve / reject / request clarification / mark not relevant / override / lock actions.
- Audit-lock snapshot capturing provenance + flags + emission factor version at lock time.

This is where data becomes trustworthy enough to be approved and locked.

**The split matters.** Mixing ingestion screens with review screens would make the dashboard look like a CRUD app over a database. Keeping them distinct makes the boundary explicit: ingestion produces candidate records, the analyst decides which ones become evidence.

---

## 3. Tenant thinking

A **tenant represents a client company, not a user**. Users (analyst, admin, reviewer) belong to a tenant; a tenant doesn't belong to a user.

In this prototype, the seeded tenant is `Demo Enterprise Client`. Every domain row — `IngestionBatch`, `RawRecord`, `NormalizedActivity`, `ValidationIssue`, `ReviewLog`, and the tenant-scoped lookup tables (`PlantLookup`, `MaterialLookup`, `UnitMapping`, `CostCenterLookup`, `MeterFacilityLookup`, `TravelCategoryMapping`) — carries a `tenant` foreign key.

I built tenant scoping into the schema even though the prototype is single-tenant in practice, because:

- SAP plant codes, material masters, utility meter IDs, and travel records are all client-specific. Mixing them across clients is a data integrity failure.
- Multi-tenant deployment later becomes a deploy-config change (real auth + tenant resolution from request), not a schema migration.
- A global lookup (like `MovementTypeMapping` or `AirportLookup`) is explicitly marked global — those don't vary by client because the underlying concepts (SAP movement types, IATA codes) aren't client-defined.

The prototype does not need a tenant-switching UI. The model proves multi-tenancy readiness; the production deployment fills in the auth + routing.

---

## 4. Mock integration strategy

I am not building live external integrations. I made that choice deliberately and the prototype reflects it:

**SAP.** Realistic MB51-like and ME2M-like CSV / Excel uploads, plus supporting lookup CSVs for plant, material, unit, movement type, and cost center.

**Utility.** Realistic utility-portal / Green Button-like CSV upload, plus a meter-to-facility lookup CSV.

**Travel.** A first-class Django endpoint at `/api/mock-travel/sync/` that behaves like a Concur / Navan API and returns realistic Concur-shaped trip JSON, including cancellations, refunds, voided bookings, codeshare duplicates, missing-distance flights, hotel-checkout edge cases, bundled packages, and unknown cabin classes.

Why I chose this over shallow live integrations:

- Real SAP OData / BAPI / IDoc requires client credentials, SAP-side configuration, network access, security approvals, and tenant-specific field mappings.
- Real utility APIs require provider-specific contracts and credentials; PDF OCR is its own document-extraction domain.
- Real Concur / Navan integration requires OAuth, sandbox provisioning, and enterprise onboarding.

For a 4-day prototype, those would have consumed the timeline on credentials and protocol plumbing while exercising none of the data-trust judgment the assignment actually grades. By matching the realistic *shape* of each source's data, I get to demonstrate the ingestion-control logic — which is the thing under test — and the transport layer becomes a swap, not a rewrite.

The full breakdown per source (what I researched, what I built, what would break in production) is in [SOURCES.md](SOURCES.md).

---

## 5. Core pipeline

Every source row passes through the same pipeline:

```
Source Input
  → RawRecord (preserve verbatim, regardless of outcome)
  → Source-specific adapter (SAP / utility / travel)
  → Eligibility filtering (ELIGIBLE / NOT_RELEVANT / NEEDS_REVIEW / FAILED / EXCLUDED)
  → Source hierarchy selection (which source-of-truth wins if duplicates exist)
  → Deduplication / reversal / cancellation handling
  → Unit and period normalization (UnitMapping, calendar-month pro-rata)
  → Validation and suspicion detection (flag set per row)
  → Confidence scoring (0–100, banded)
  → Optional Groq LLM suggestion (only for LOW band, text fields only)
  → NormalizedActivity (the single shape the dashboard reads)
  → Analyst Review Dashboard
  → Approval / Rejection / Clarification request / Override
  → Audit Lock (frozen snapshot of provenance + flags + EF version)
```

The non-negotiable: **every source row is stored unchanged as a `RawRecord`, including failed and excluded rows**. If an analyst challenges a decision six weeks after ingestion, I point at the raw row. If I find an adapter bug, I reprocess from raw without re-asking the client for the file.

---

## 6. SAP approach

I chose SAP MM Material Documents / Goods Movements as the primary SAP subset. The two export shapes I support:

- **MB51-like** — material movement list, the primary fuel-activity source.
- **ME2M-like** — procurement by material, the spend-based fallback when no consumption record exists.

**Why MM movements.** Fuel emissions live in MM because that's where goods issues, receipts, transfers, reversals, and scrap appear. The fields I need for Scope 1 are all there: `Material`, `Quantity`, `Unit`, `Plant`, `Posting Date`, `Movement Type`, `Document Number`, `Cost Center`.

**The key SAP insight.** Not every SAP row is carbon-relevant. MB51 contains all goods movements, not just consumption — and a naive ingester that sums quantity per material across the file will double- or triple-count fuel.

My movement-type filter:

- `261` / `201` → fuel **consumption**, ESG-relevant.
- `101` → goods **receipt** — fuel arrived, not burned. Classified as `fuel_purchased`, routed to NEEDS_REVIEW.
- `301` / `311` → stock **transfer** — inventory movement, not an emission. Excluded.
- `551` → **scrapping / write-off** — flagged for analyst review.
- `262` → **reversal** of a 261 — linked to the original document, netted.
- Unknown movement type → routed to analyst review with `UNSUPPORTED_MOVEMENT_TYPE`.

**Purchase ≠ consumption.** A company can buy 10,000 L of diesel in January and burn 6,000 L of it. If I count the purchase as the emission, January is overstated and February is understated. My source hierarchy:

1. Actual consumption / meter log.
2. Goods issue / tank issue.
3. Purchase invoice (weakest; used only when nothing better exists).

**SAP data-quality issues I designed for:**

- German headers (`Buchungsdatum`, `Werk`, `Bewegungsart`, `Menge`, `ME`) coexist with English in multinational deployments.
- Mixed date formats (`DD.MM.YYYY`, `MM/DD/YYYY`, `YYYY-MM-DD`, `YYYYMMDD`).
- European and US numeric formats sniffed per column.
- Unknown plant codes routed to `MISSING_FACILITY_MAPPING`.
- Unknown material codes flagged for analyst classification.
- Inconsistent units (`L`, `KG`, `M3`, `GAL`, `TO`, `MJ`, `ST`, `RM`) normalized via `UnitMapping`; unknown units fail loud.
- Duplicate document numbers (same `Belegnummer` twice in one file) flagged.
- Suspicious-high quantities (e.g. 50,000 L of diesel in a single goods issue) flagged.
- Stock transfers excluded with structured exclusion reason.
- Reversals (262 / 202 / 102) linked to their parents.
- Procurement rows in non-energy units (`ST`, `RM`) drop to spend-based, capped at confidence 60.

---

## 7. Utility approach

I chose CSV upload over PDF OCR or a live utility API. Facilities teams routinely download portal exports; PDF utility bill extraction is its own OCR / layout-parsing domain that would consume the prototype budget without exercising any ESG judgment.

**The key utility insight.** Don't extract only the total amount due. The total amount is what finance cares about; ESG needs `usage_kwh`, `meter_number`, billing period, reading type, tariff, and demand. A bill with only the total is a spend-based fallback row, not a real consumption record, and the system has to mark it as such.

Utility data is **billing-period based, not transaction-date based**, and bill cycles rarely align with calendar months. So I built:

- **Calendar-month pro-rata.** A Dec 28 → Jan 27 bill becomes two `NormalizedActivity` rows: one for December (4 days, scaled usage), one for January (27 days, scaled usage). Each carries its own `calendar_month`.
- `billing_days` and `usage_per_day` stored on every row. Spike detection runs on `usage_per_day`, so a 33-day bill doesn't false-positive against a 28-day baseline.
- **Estimated readings** flagged `ESTIMATED_READING`, marked `is_estimate=true`, confidence capped at 70 (MEDIUM band).
- **Overlapping billing periods** detected for the same meter — typically an amended/correction bill — flagged `POSSIBLE_AMENDED_BILL` for analyst reconciliation.
- **Amount-only rows** flagged `TOTAL_AMOUNT_ONLY`, demoted to spend-based, confidence capped.
- **Gas rows** (`therms`, `CCF`, `m3 gas`) arriving in an electricity import are rejected outright with `GAS_UTILITY_DATA_DETECTED`. Silent unit confusion is the most expensive failure mode in this domain — wrong by roughly an order of magnitude.
- **Multiple meters per site** kept as separate normalized records; aggregated at query time, not at ingestion. `MULTIPLE_METER_SITE` flagged for analyst awareness.
- **Tax-only, late-fee-only, payment-only, deposit-only, refund-only, adjustment-only rows** filtered as `NOT_RELEVANT` with structured exclusion reasons.

---

## 8. Travel approach

I chose a mocked API pull because travel platforms (Concur, Navan, Egencia) expose structured trip / booking / itinerary data through REST APIs. The mock endpoint returns the shape a real provider would return — segment-typed records with `segment_type`, `booking_status`, `leg_id`, `ticket_number`, `cabin_class`, origin, destination, distance, dates.

Travel covers flights, hotels, car rentals, rail, rideshare / taxi, expense-only rows, and cancelled / refunded bookings.

**The key travel insight.** **A booking is not actual travel.** Cancelled, refunded, voided, and no-show bookings appear in the same date range as completed ones, and the sustainability layer has to filter them out itself.

My travel rules:

- **Cancellation / refund / void filtering.** These rows stay as `RawRecord` with structured `exclusion_reason`, never become a `NormalizedActivity`.
- **Expense-only rows with no travel segment** excluded.
- **Leg grouping** by `leg_id` (with a 6-hour-gap fallback when `leg_id` is missing). One emission record per leg, summing distances of segments within the leg.
- **No double-counting** of round trips when both legs are already separate entries.
- **Flight distance**: provided field > haversine via `AirportLookup` IATA coordinates > `MISSING_FLIGHT_DISTANCE`. The LLM is not allowed to invent distance.
- **Cabin class** mapped from booking class codes (`Y/B/M/H/Q/K/L/U/T/X/V` → economy, `W/S/E` → premium economy, `C/D/I/J/Z` → business, `F/A/P` → first). Unknown codes default to economy + `UNKNOWN_CABIN_CLASS` flag + lower confidence.
- **Hotel room-nights** = `(check_out − check_in) × room_count`. Missing checkout → `MISSING_CHECKOUT`, blocked. Same-day → `ZERO_ROOM_NIGHTS`.
- **Room-nights ≠ employee-nights.** Two employees sharing one room for three nights is three room-nights, not six.
- **Hotel spend** fallback excludes taxes, food, laundry, minibar where itemized; bundled packages flagged `BUNDLED_TRAVEL_PACKAGE` and routed to review.
- **Rental car double-count prevention.** Same-city pickup/dropoff flagged `RENTAL_CAR_DOUBLE_COUNT_RISK` — if the employee also submits a fuel receipt, that's two emissions for the same activity.
- **Business travel vs commute** distinguished by `scope_category` (`3.6 business travel` vs `3.7 employee commuting`).
- **Codeshare duplicates** detected on `(departure_datetime, origin, destination, distance_km)` — the same physical flight appearing under two carrier tickets — flagged `POSSIBLE_CODESHARE_DUPLICATE`.

---

## 9. Normalized data model

Every eligible source row, regardless of origin, lands in one central model: `NormalizedActivity`. This is the model the analyst dashboard reads from. Unifying SAP, utility, and travel into a single activity shape is what makes the review workflow source-agnostic.

The fields it carries (full detail in [MODEL.md](MODEL.md)):

- **Identity / lineage.** `tenant`, `batch`, `raw_record` — every normalized row points back to its raw source.
- **Classification.** `source_type`, `activity_type`, `activity_subtype`, `scope`, `scope_category`.
- **Eligibility & method.** `eligibility_status`, `source_hierarchy_rank`, `source_of_truth`, `activity_basis`, `calculation_method`, `emission_method`.
- **Time.** `activity_date`, `period_start`, `period_end`, `calendar_month`, `billing_days`.
- **Location.** `facility_code`, `facility_name`, `facility_country`, `origin`, `destination`.
- **Quantity stored twice.** `quantity` + `unit` (raw, as ingested) and `normalized_quantity` + `normalized_unit` (after `UnitMapping`). The raw pair is for audit; the normalized pair is what the emission factor multiplies against.
- **Spend.** `currency`, `amount` — populated regardless of method, used directly only for spend-based rows.
- **Context.** `vendor`, `cost_center`, `reference_id`, `event_key`, `parent_event_key`.
- **Dedup / reversal / estimate flags.** `is_duplicate`, `is_reversal`, `reversal_of`, `is_estimate`, `estimate_reason`, `requires_reconciliation`.
- **Emissions.** `emission_factor`, `emission_factor_source`, `co2e_kg`.
- **Quality.** `data_quality_score` (0–100), `confidence_level` (HIGH/MEDIUM/LOW/FAILED), `method_confidence`, `flags` (JSON list), `field_provenance` (JSON map), `llm_suggestions`, `llm_suggestion_reviewed`.
- **Review workflow.** `review_status`, `reviewed_by`, `reviewed_at`, `review_comment`, `approved_by`, `approved_at`, `locked_at`, `locked_snapshot`.

The related models orbit `NormalizedActivity`:

- **`Tenant`** — the multi-tenancy boundary.
- **`IngestionBatch`** — the unit of work; carries funnel counts and the lookup versions in effect at ingestion time (so audit reconstruction survives lookup drift).
- **`RawRecord`** — every source row preserved verbatim, with `parse_status`, `eligibility_status`, structured `exclusion_reason`.
- **`ValidationIssue`** — per-record findings with severity (ERROR / WARNING / INFO), queryable as a journal.
- **`ReviewLog`** — append-only audit trail of every analyst action.
- **Lookup tables** — `PlantLookup`, `MaterialLookup`, `UnitMapping`, `MovementTypeMapping` (global), `CostCenterLookup`, `MeterFacilityLookup`, `AirportLookup` (global), `CityCodeLookup` (global), `TravelCategoryMapping`, `EmissionFactorMapping` (global).

---

## 10. Field-level provenance

For every important normalized field, I record **how** that value was derived. Provenance is a property of the record, not a log entry.

The methods:

- **`DIRECT`** — value came straight from the source row (e.g. `quantity` from SAP `Menge`).
- **`RULE_BASED`** — value was derived by a deterministic lookup or transformation (e.g. `normalized_unit` from `UnitMapping:L→litres`, `facility_name` from `PlantLookup:1000→Hamburg Factory A`).
- **`LLM_SUGGESTED`** — value was suggested by Groq and is awaiting analyst review.
- **`MISSING`** — value couldn't be determined; analyst attention required.
- **`ANALYST_OVERRIDDEN`** — analyst manually set this value (also what an accepted LLM suggestion becomes).

Trust hierarchy: `DIRECT > RULE_BASED > ANALYST_OVERRIDDEN > LLM_SUGGESTED > MISSING`.

Example for a SAP fuel consumption row:

```json
{
  "quantity":        { "method": "DIRECT",    "source_field": "Menge",             "confidence": 1.0 },
  "normalized_unit": { "method": "RULE_BASED","rule": "UnitMapping:L->litres",     "confidence": 1.0 },
  "facility_name":   { "method": "RULE_BASED","rule": "PlantLookup:1000->Hamburg", "confidence": 0.95 },
  "activity_subtype":{ "method": "LLM_SUGGESTED","confidence": 0.72,
                       "reason": "Material description contains HSD and genset fuel; mapped to diesel" },
  "facility_name?":  { "method": "MISSING",   "reason": "Plant DE03 not in lookup" }
}
```

**Why provenance is a stored field and not just log output:** analysts and auditors need to see *why* a value is what it is, inline on the row detail view. The audit lock snapshots it. Provenance is what makes the system explainable; without it, an "approved" record is a black box.

---

## 11. Confidence scoring

Every row is scored 0–100. I start at the method ceiling (100 for fuel-based, 95 for distance-based or location-based-Scope2, 90 for room-night-based, 60 for spend-based) and subtract a fixed amount per flag. The final score buckets into:

- **80–100 → HIGH.** Ready for analyst approval; deterministic mappings worked.
- **50–79 → MEDIUM.** Needs review; some flags applied (estimated reading, suspicious-but-handled, etc.).
- **30–49 → LOW.** Eligible for Groq LLM suggestion; deterministic path failed but row still has useful context.
- **<30 → FAILED.** Not safely normalizable; no audit-ready record produced.

Sample deductions (full table is in [DECISIONS.md](DECISIONS.md) and `services/confidence.py`):

- Unresolved activity type: −20.
- Missing or zero quantity: −20.
- Unknown unit: −15.
- Missing date / period: −15.
- Unresolved facility: −15.
- Missing source reference: −10.
- Estimated reading: −10 (and confidence capped at 70).
- Distance estimated (haversine): −5.
- Spend-based method: built into the 60 method ceiling, not an extra deduction.
- LLM-suggested field: −10.
- Suspicious-high quantity: −10.
- Unresolved duplicate or reversal: −20.
- Unresolved cancelled or refunded: −20.

**Why a number and bands instead of just flags or an ML score:**

- Bands are the unit the analyst thinks in.
- The number is what the system sorts on (focus attention on the lowest-quality rows).
- The audit lock can be gated on a minimum threshold.
- Every score is reconstructible from `flags` alone — that's what makes it defensible to an auditor.

---

## 12. Groq LLM integration

Groq is an **optional assisted reasoning layer**, not a source of truth. The implementation is intentionally narrow.

**Where it lives.** The backend calls Groq via the official `groq` SDK, gated on `GROQ_API_KEY`. If the key is absent, the system skips LLM suggestions gracefully and the row goes to manual review — no failure cascade.

**When it triggers.** Only for LOW-band rows (confidence 30–49) where deterministic mapping failed but the raw row still has useful text context (a material description, a vendor name, a free-text note). The analyst can also force it on a MEDIUM row from the UI.

**What Groq is allowed to do:**

- Classify ambiguous SAP material descriptions (`"HSD GENSET FUEL"` → diesel).
- Suggest a fuel or material category.
- Suggest a spend category for procurement spend-based rows.
- Judge whether a text-heavy row is ESG-relevant.
- Explain why a row is low confidence in human-readable terms.
- Suggest what additional data the analyst should request from the client.

**What Groq is forbidden to do (enforced in code, not just in the prompt):**

- Generate quantity values.
- Generate dates.
- Generate invoice / document / bill / ticket / confirmation / reference numbers.
- Generate kWh, room-nights, or flight distance.
- Approve or lock records.
- Override deterministic rule-based mappings.

The response parser inspects every suggestion before storing it. Suggestions for any field in the forbidden set are dropped and a note is added to the response. Allowed suggestions land in `field_provenance` as `method: LLM_SUGGESTED`.

**Analyst gating.** A row with unreviewed LLM suggestions cannot be locked. Accepting a suggestion flips its provenance to `ANALYST_OVERRIDDEN`. Rejecting a suggestion logs the rejection in `ReviewLog`.

**Caching.** Per `(raw_record_id, missing_fields_hash)`, so re-opening the same activity doesn't trigger repeat paid calls.

**Why this design.** LLMs reason well over text and hallucinate aggressively over numerics. The boundary between assist and fabricate is the boundary between text classification and numeric generation. I enforce that boundary in code, not just in prompting, because prompts drift and grading doesn't.

---

## 13. Analyst review and audit lock

Approval and audit lock are **two distinct actions**.

**Approval** means: "I, the analyst, have reviewed this row and agree it is acceptable." It sets `review_status = APPROVED`, records the reviewer and timestamp, and (optionally) attaches a comment. An approved row is not yet immutable.

**Audit lock** means: "This approved row is now frozen evidence and cannot be silently changed." It sets `locked_at`, writes a `locked_snapshot` JSON capturing the record's state, and the API rejects any further mutation.

Why they're separate: approval is a per-row analyst decision that can be revisited (with a fresh review log entry). The lock is a deliberate, often-batched action that signals "this is the version we'd stand behind in an audit, an investor disclosure, or a compliance review."

**The locked snapshot stores:**

- `approved_by` and `approved_at`.
- `locked_at`.
- The review comment chain.
- The raw record reference.
- The full `field_provenance` map at lock time.
- The active `flags` list.
- The eligibility decision and source-hierarchy rank.
- The emission factor value, source, and version.
- The `co2e_kg` value.
- The list of active validation issue codes.

If a plant lookup is amended six months after lock or an emission factor is bumped to a new version, the locked row's snapshot still answers "what was this number based on?" That reconstructibility is the entire point of the lock.

---

## 14. Deployment

**Backend.** Django + Django REST Framework + PostgreSQL.

**Frontend.** React + Vite + TypeScript + Tailwind.

**LLM.** Real Groq API behind `GROQ_API_KEY`; graceful skip if absent.

**Travel.** First-class Django endpoint `/api/mock-travel/sync/` returning Concur / Navan-shaped JSON.

**Deployment target.** Render, configured via `render.yaml`:

- One web service.
- One Render Postgres add-on.
- Frontend built (`npm run build`) and served by Django via WhiteNoise from the same origin — no CORS configuration needed.
- One public URL serves both `/api/*` and the React SPA (with client-side routing via a catch-all).
- Build script runs `pip install` → `npm run build` → `collectstatic` → `migrate` → `seed_tenant` → `load_lookups`.
- `Procfile` provided as a fallback for Railway / Fly.io.

**Tenant.** One seeded — `Demo Enterprise Client`. Two seeded users for Django admin only (`admin` / `admin`, `analyst` / `analyst`). The app itself is unauthenticated by design — see Tradeoff 3.

---

## 15. Tradeoffs

The main tradeoffs I made were not only technical shortcuts. Most of them were data-trust decisions: when to trust a source row, when to exclude it, when to estimate, and when to force analyst review. Full reasoning is documented in [TRADEOFFS.md](TRADEOFFS.md).

---

### Tradeoff 1 — Source availability vs data quality

Client data may arrive in different levels of completeness. Some clients may provide rich activity data such as fuel quantity, unit, plant, movement type, meter number, or travel segment. Others may provide weak invoice-level or amount-only records.

I chose to support both, but not treat them equally.

High-quality physical activity data becomes the preferred source. Weak spend-only or invoice-only data is preserved, normalized where possible, but marked lower confidence.

Examples:

- SAP goods issue with fuel quantity and unit → stronger evidence.
- SAP purchase invoice only → weaker evidence.
- Utility kWh with meter and billing period → stronger evidence.
- Utility total amount only → weaker evidence.
- Travel segment with route/distance/nights → stronger evidence.
- Travel expense amount only → weaker evidence.

This keeps the system useful even when client data is incomplete, but prevents weak data from looking audit-ready.

---

### Tradeoff 2 — Purchase data vs actual consumption

A purchase is not always an emission event.

For fuel, SAP may show that diesel was purchased or received into inventory, but that does not mean it was burned in the same reporting period. Counting purchase rows as Scope 1 emissions can overstate emissions or double-count when actual consumption data also exists.

I used a source hierarchy:

1. actual consumption / meter / fuel log,
2. goods issue / tank issue,
3. purchase invoice as fallback.

This means goods receipt and invoice records are useful for reconciliation, but actual consumption-like records are preferred for emissions.

The tradeoff is that I may delay or downgrade some purchase records instead of immediately converting them into emissions. That is intentional because accuracy and auditability matter more than maximizing row count.

---

### Tradeoff 3 — Ingest every row vs filter ESG-relevant rows

I decided not to blindly convert every incoming SAP, utility, or travel row into a `NormalizedActivity`.

Every raw row is preserved, but only ESG-relevant rows become reviewable activity records.

Examples:

- SAP `101` goods receipt is stored but not counted as fuel consumption.
- SAP `311` stock transfer is stored but excluded from emissions.
- Utility tax-only or late-fee-only rows are stored but marked not relevant.
- Cancelled or refunded travel bookings are stored but excluded.
- Expense-only travel rows without a travel segment are stored but not treated as travel activity.

This tradeoff reduces false positives and double counting. The cost is that the ingestion pipeline needs stronger eligibility rules and exclusion logs.

---

### Tradeoff 4 — Rule-based logic vs LLM-assisted reasoning

I used deterministic rules first and Groq only as a controlled fallback.

Direct source mapping and lookup tables are more auditable than LLM output. Groq is used only when the row is low-confidence, rule-based mapping failed, and the raw data still contains useful text context.

Groq can suggest classifications such as material category or spend category, but it cannot generate quantities, dates, document numbers, kWh, distances, or audit references.

This tradeoff keeps the benefits of AI without allowing AI to become the source of truth.

The boundary is:

- rules handle numeric and auditable transformations,
- Groq helps with ambiguous text interpretation,
- analysts approve or reject every suggestion.

---

### Tradeoff 5 — Confidence threshold vs API cost

Using Groq for every row would be expensive and unnecessary. Most rows can be handled through direct mapping or deterministic rules.

I introduced confidence thresholds:

- high confidence rows go directly to analyst approval,
- medium confidence rows need review,
- low confidence rows may trigger Groq,
- failed rows stay manual.

This saves API cost and keeps AI usage explainable. The tradeoff is that some rows that might benefit from AI will still be handled manually if they do not meet the threshold.

I chose this because the system should use LLMs selectively, not as a default parser.

---

### Tradeoff 6 — Normalize into one model vs preserve source-specific context

The system needs one unified `NormalizedActivity` model so analysts can review SAP, utility, and travel records in one dashboard.

But each source has unique context:

- SAP has movement types, material codes, plant codes, reversals.
- Utility has meters, billing periods, estimated readings, usage per day.
- Travel has segments, booking status, cabin class, room nights, leg grouping.

I chose a common normalized model plus source-specific fields, flags, provenance, and raw payload preservation.

This gives the analyst one review experience without losing source-specific meaning.

---

### Tradeoff 7 — Utility bill amount vs actual energy usage

A utility bill total is useful for accounting, but it is not enough for ESG.

I chose `usage_kwh`, billing period, meter number, and reading type as the main utility fields. Amount-only rows are preserved but marked low confidence.

This prevents the system from treating financial charges, taxes, deposits, late fees, or previous balances as energy consumption.

The tradeoff is that some utility records cannot become high-confidence ESG activity unless the client provides actual usage data.

---

### Tradeoff 8 — Billing-period accuracy vs implementation complexity

Utility bills do not align cleanly with calendar months. I chose to prorate usage across calendar months based on billing days.

This is not perfect because real usage may vary by weather, weekday/weekend patterns, occupancy, or production cycles. But without interval data, day-based prorating is more accurate than assigning the full bill to a single month.

I also calculate `usage_per_day` so a 35-day bill is not unfairly compared with a 28-day bill.

This is a practical tradeoff between correctness and available data.

---

### Tradeoff 9 — Travel booking data vs completed travel evidence

A travel booking is not always actual travel.

Flights can be cancelled, hotels can be refunded, and bookings can be voided. I chose to preserve these records as raw evidence but exclude them from normalized emissions activity.

This avoids overstating Scope 3 business travel emissions.

The tradeoff is that the adapter must track booking status and exclusion reasons rather than simply counting every travel record returned by the API.

---

### Tradeoff 10 — Simple approval vs audit lock

Approval and audit lock are separate.

Approval means an analyst accepts the row. Audit lock means the row becomes frozen evidence for reporting or audit.

I chose to separate them because approved ESG data may later be used in reports, auditor review, investor disclosures, or compliance workflows. Once locked, the record should not be silently changed.

The tradeoff is extra workflow complexity, but it gives a stronger audit trail.

---

### Tradeoff 11 — Mock integrations vs real integration setup

I did not build live SAP, utility, or travel integrations.

Instead:

- SAP uses realistic MB51/ME2M-style CSV uploads.
- Utility uses realistic portal/Green Button-like CSV uploads.
- Travel uses a mocked Concur/Navan-like API endpoint.

Real integrations require credentials, security review, OAuth, sandbox access, and tenant-specific setup. For this prototype, I chose to prove the ingestion-control logic using realistic data shapes.

The adapter design keeps the transport layer replaceable later. A real SAP OData client or Concur OAuth client can replace the mock/file input without changing the normalized model or analyst workflow.

---

### Tradeoff 12 — Emission calculation depth vs ingestion trust

I kept emission calculations intentionally minimal.

The assignment’s core problem is messy source data, not building a full carbon factor engine. I use a small `EmissionFactorMapping` table with illustrative factors so the flow from activity to `co2e_kg` is visible, but the main effort is on:

- raw record preservation,
- eligibility filtering,
- unit normalization,
- confidence scoring,
- field provenance,
- analyst review,
- audit lock.

A production emission factor engine would need factor versioning, country/grid-specific factors, market-based Scope 2 evidence, supplier-specific factors, and uncertainty handling. That is a separate workstream.

---

### Tradeoff 13 — Multi-tenancy schema vs full tenant management UI

I added a `Tenant` model because each client company has its own data, mappings, uploads, and review history.

For the prototype, I seed one tenant: `Demo Enterprise Client`.

I did not build tenant switching, invitations, user pools, or full RBAC. But every major domain model is tenant-scoped, so multi-tenancy is supported in the schema.

This proves the data model is ready for multiple client companies without spending the prototype budget on account-management UI.

---

### Tradeoff 14 — Functional analyst UX vs visual polish

I prioritized analyst clarity over visual polish.

The UI focuses on:

- what came in,
- what failed,
- what was excluded,
- what needs review,
- why a row is suspicious,
- where each value came from,
- what action the analyst should take.

I used clear cards, filters, badges, raw-vs-normalized comparison, validation messages, provenance tables, and review actions.

I did not prioritize animations, a custom design system, or decorative UI because those do not improve data trust.

---

### Tradeoff 15 — Synchronous ingestion vs production-grade background jobs

The prototype processes uploads synchronously.

For the sample file sizes, this is acceptable and keeps deployment simple on Render.

In production, file ingestion should move to background workers with queue-based processing, progress tracking, retries, and partial failure recovery.

I chose synchronous processing because the prototype’s goal is to demonstrate ingestion logic, not infrastructure scale.

---

## 16. Final positioning

This prototype is a **layered ESG ingestion and review system**. It converts messy SAP, utility, and travel source data into validated, provenance-tracked, analyst-approved activity records before audit.

The core value is not the dashboard alone. The core value is the **ingestion-control layer**: deciding which rows matter, which rows are suspicious, which values are direct or derived, and which records are trustworthy enough for analyst approval.

What makes that defensible:

- Every source row is preserved, regardless of outcome.
- Every eligibility decision is explicit and structured.
- Every transformation has a stored reason (provenance).
- Every confidence score is reconstructible from flags.
- Every analyst action writes to an append-only log.
- Every locked record carries a frozen snapshot that survives downstream config drift.
- LLM assistance is text-only, analyst-gated, and never reaches a locked record without explicit human acceptance.

If an evaluator asks "why did you do X?", the answer is in one of these documents — and the design choices hold up to that question because that's the question I asked myself before I made each one.
