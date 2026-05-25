# Breathe ESG — Source Inputs

For each source I had to answer three questions: what does the real production format look like, what's the cheapest way to exercise the pipeline against something that behaves like it, and what would break the day we connect the real system?

---

## 1. SAP — fuel and procurement

**What I researched.**
SAP ERP exposes goods-movement and procurement data through several mechanisms:

- **MB51** — interactive transaction for material document lists; Excel/CSV export. The standard way an operations or sustainability user pulls a fuel movement report.
- **ME2M** — purchasing documents by material; CSV/Excel export.
- **OData / SAP Gateway** — REST endpoints over MM (movements, POs, GRs). Needs Gateway configured and corporate network reachability.
- **IDoc / RFC / BAPI** — middleware integration; needs SAP-side configuration and a broker.
- **SE16N / direct table reads** — MSEG, EKKO/EKPO. Power-user territory.

In practice, onboarding starts with an MB51 Excel export from a localized SAP UI (often German — `Buchungsdatum`, `Werk`, `Bewegungsart`).

**What the prototype uses.**
CSV upload at `POST /api/ingestion/sap/upload/`. The adapter handles English and German headers (auto-detected), mixed date formats (`DD.MM.YYYY`, `MM/DD/YYYY`, `YYYYMMDD`, `YYYY-MM-DD`), EU and US numeric formats sniffed per column, SAP unit codes mapped through `UnitMapping`, and movement-type filtering through `MovementTypeMapping` (261/201 → consumption, 101 → fuel_purchased, 311/301 → excluded, 551 → review, 262 → reversal linked to its parent, unknown → review).

ME2M procurement rows in non-energy units (`ST`, `RM`, `BOX`, `EACH`) drop to spend-based, capped at confidence 60.

**Sample data — `backend/fixtures/sap/`:**

| File | Edge cases it exercises |
|---|---|
| `sap_mb51_fuel_movements.csv` | 28 rows: German headers, EU-style dates, 261/201 consumption, 101 receipt (excluded), 311/301 transfers (excluded), 551 scrap (review), 262 reversal of a 261, duplicate document, suspicious-high quantity (50,000 L), zero / negative / missing quantities, missing posting date, unknown plant `DE03`, unknown material code, units L/KG/M3/GAL. |
| `sap_me2m_procurement.csv` | 10 procurement rows in `ST` / `RM` (spend-based) alongside `L` / `M3` / `GAL` (fuel-purchase); mixed currencies EUR/USD/GBP/INR. |
| `plant_lookup.csv` | 6 plant codes → facility/country. Plant `DE03` appears in MB51 but is intentionally absent here, to exercise `MISSING_FACILITY_MAPPING`. |
| `material_lookup.csv` | Material → fuel_type / default_unit / density. `MAT-1004 "HSD Genset Fuel"` is included so the Groq path can demonstrate text-to-fuel-type inference. |
| `unit_mapping.csv` | 15 unit codes with conversion factors (GAL → 3.785 L, MJ → 0.278 kWh, etc.). |
| `movement_type_mapping.csv` | 12 movement types with ESG relevance + default action. Global, not tenant-scoped. |
| `cost_center_lookup.csv` | 6 cost-center codes → business unit / region. |

**Why this is realistic.**
- Real MB51 exports mix consumption, receipts, transfers, reversals, and scrap in one file; the adapter must filter, not sum.
- German + English header coexistence reflects multinationals where SAP UI language follows the user, not the company.
- The 261 / 262 reversal pair is a documented SAP pattern; netting them is not optional.
- EU numeric format (`5.000,00`) is the dominant case in DACH customer files.

**What would break in real deployment.**
- Per-customer custom Z-fields (`ZZ_VEHICLE_ID`) — would need tenant-level column mapping config.
- S/4 HANA renamed fields — minor mapping additions.
- Files >100k rows — synchronous processing would time out; production needs queue-based ingestion.
- Live OData / RFC sync — replaces the upload endpoint; downstream adapter logic is unchanged.

---

## 2. Utility — electricity

**What I researched.**
Electricity usage data reaches sustainability teams via:

- **Utility portal CSV / Excel exports.** Account, meter, billing period, usage, demand, charges, reading type. Field sets vary across providers but the core columns converge.
- **Green Button (CSV / XML).** US-originated open standard, increasingly adopted globally. Bill-level and interval data.
- **EDI 867.** Utility-to-customer-of-record EDI. B2B-focused, not seen in onboarding handoffs.
- **PDF bill scans.** Common when there's no portal access. Extraction is its own OCR/layout problem — out of scope here.
- **Direct utility API.** Rare; most that do exist go through Green Button Connect.

In practice, the file I get during onboarding is a portal CSV — sometimes literally named `"Account_<n>_Usage_2024.csv"`.

**What the prototype uses.**
CSV upload at `POST /api/ingestion/utility/upload/`. The adapter handles:

- Meter / account → facility resolution via `MeterFacilityLookup`, identity tuple `(provider, account_number, meter_number)`.
- Charge-type filter: drop tax-only, late-fee-only, payment-only, deposit, adjustment-only, refund.
- Billing period validation: end-before-start, too-long (>40d), too-short (<25d), overlapping with another period for the same meter.
- **Calendar-month pro-rata:** a Dec 28 → Jan 27 bill produces two `NormalizedActivity` rows, one for each month, with `usage_kwh` scaled by `days_in_month / total_days`.
- `usage_per_day = usage_kwh / billing_days` for spike detection that doesn't false-positive on 33-day vs 28-day cycles.
- Estimated readings flagged `ESTIMATED_READING`, `is_estimate=true`, confidence capped at 70.
- Multiple meters at the same site kept as separate normalized records; aggregated at query time.
- Gas rows (`therms`, `CCF`, `m3 gas`) rejected with `GAS_UTILITY_DATA_DETECTED` — never silently converted.

**Sample data — `backend/fixtures/utility/`:**

| File | Edge cases it exercises |
|---|---|
| `utility_electricity_export.csv` | 23 rows: two meters at the same Hamburg site, one estimated reading overlapped by an actual (amended-bill case), 33-day and 29-day periods, a Dec→Jan straddler, zero kWh, negative kWh, tax-only, late-fee-only, amount-only adjustment, refund, unmapped meter `MTR-1003`, four sites (Hamburg + London + Chicago + Mumbai + Munich), and a deliberately misplaced gas row in therms. |
| `meter_facility_lookup.csv` | 6 meter rows. Includes both Hamburg meters + the London/Chicago/Mumbai/Munich meters; deliberately omits `MTR-1003` and the gas meter so the exclusion paths fire. |

**Why this is realistic.**
- Two meters at one address is the normal case for industrial / hospital / campus sites.
- A bill straddling calendar months is also the normal case — bill cycles align to meter-read dates.
- Estimated readings followed by amended actuals is a documented scenario the dashboard needs to surface.
- A stray gas row happens when a customer downloads "all my utility data" from a portal that bundles services.

**What would break in real deployment.**
- Interval data (15-min / hourly) — current model is bill-level. Adds two orders of magnitude in row count; needs a separate model.
- Time-of-use rate splits (on-peak / off-peak / shoulder) — currently flattened.
- Demand-charge ESG treatment (some methodologies penalize peak demand) — `demand_kw` stored but unused.
- Cross-currency spend-based fallback — no FX layer.

---

## 3. Corporate travel

**What I researched.**
Business-travel data reaches sustainability teams via:

- **Concur Travel APIs.** REST; OAuth 2.0; per-customer contracts.
- **Navan APIs.** Similar REST shape; trip + segment + booking + traveler records.
- **Egencia (Amex GBT) APIs.** Enterprise; API or SFTP CSV drops.
- **Internal expense systems** (SAP Concur Expense, Workday Spend, Coupa) — gap-fill for non-platform bookings.
- **Quarterly CSV drops.** Mid-market default.

Large enterprises in 2025 are usually API-based (Concur and Navan dominate); mid-market is usually CSV-based.

**What the prototype uses.**
A mock API at `GET /api/mock-travel/sync/?start_date=&end_date=` returning JSON shaped like Concur/Navan. The travel ingestion endpoint (`POST /api/ingestion/travel-sync/`) calls this internally.

The adapter handles:

- Per-segment normalization (`flight`, `hotel`, `car_rental`, `rail`, `rideshare`, `expense`).
- Cancellation / refund / void filtering — rows stay as `RawRecord` with `exclusion_reason`, never become `NormalizedActivity`.
- Leg grouping by `leg_id` (or 6-hour-gap fallback when missing).
- Cabin-class mapping with documented defaults; unknown codes default to economy + flag.
- Distance: provided field → haversine via `AirportLookup` IATA coordinates → MISSING. LLM is not allowed to invent distance.
- Hotel room-nights = `(check_out - check_in) * room_count`. Missing check-out → blocked. Same-day → `ZERO_ROOM_NIGHTS`.
- Codeshare dedup on `(departure_datetime, origin, destination, distance_km)`.
- Car rental: fuel > distance > spend fallback. Same-city pickup/dropoff → `RENTAL_CAR_DOUBLE_COUNT_RISK`.
- Rail: distance > city-code haversine > MISSING.
- Rideshare / taxi: distance > spend (capped at 40). Amount-only → flagged.
- Expense-only segments with no travel basis: excluded.

**Sample data — `backend/fixtures/travel/mock_response.json`** (20 trips, 28 segments, filtered by date range at the endpoint):

- Round-trip flight (two legs, both with `leg_id`).
- Connecting flight LHR → DXB → BOM sharing one `leg_id`.
- Cancelled, refunded, and voided bookings — all excluded.
- Codeshare duplicate (same Lufthansa-operated flight on a UA-prefixed and an LH-prefixed ticket).
- Flight missing `distance_km` but with IATA codes → haversine fires.
- Flight missing both distance and IATA codes → `MISSING_FLIGHT_DISTANCE`.
- Valid 2-night hotel; hotel missing check-out; same-day hotel; bundled flight+hotel package.
- Car rental same city (double-count risk) and different cities (distance-based).
- Rideshare with amount only.
- Expense-only row with no segment.
- Cabin classes covering economy, premium economy, business, first, and unknown.

Plus `backend/fixtures/lookups/airport.csv` with ~80 IATA codes (lat/lon/country) covering every airport referenced in the mock response.

**Why this is realistic.**
- Concur/Navan responses mix completed and cancelled bookings in the same date range; the sustainability layer has to filter.
- Codeshare duplicates are a real double-count source.
- Bundled packages from third-party booking sites arrive as a single line item without itemization.
- Cabin-class inconsistency across airline integrations is documented; defaulting to economy + flagging is the safe path.

**What would break in real deployment.**
- OAuth handshake and refresh-token rotation against the real provider.
- Pagination on large date ranges — the mock returns everything in one response.
- Per-tenant API credentials and secret storage.
- Provider-specific field names — every platform uses slightly different keys.
- Rate limiting and retries against external SLAs.

---

## 4. Groq LLM — optional reasoning layer

**What I researched.**
LLMs in ESG ingestion in 2025 are used for:

- Text classification of ambiguous activity descriptions (SAP material descriptions, GL codes, vendor categorization).
- Spend category inference from supplier + invoice description for spend-based Scope 3.
- Document extraction from PDFs (a separate domain — not in this prototype).
- Anomaly explanation — turning "this row is suspicious" into a human-readable reason.
- Drafting the question the analyst should ask the client.

The shared rule in every system I'd respect: **the LLM never generates numeric source-of-truth values**.

**What the prototype uses.**
Real Groq API via the official `groq` SDK, called from `backend/activities/services/groq_suggestion.py`:

- Invoked when confidence is in the LOW band (30–49) and deterministic mapping has failed. Analyst can also force it from the UI.
- Sends source type, raw payload, partial normalized record, missing fields, validation flags, and a small slice of lookup context.
- JSON-mode response with a defined schema (suggestions array; per-suggestion field, suggested_value, confidence, reason).
- The response parser drops any suggestion targeting a forbidden field (quantity, dates, identifiers, distances, amounts) and records a note.
- Cached per `(raw_record_id, missing_fields_hash)` in `GroqSuggestionCache`.
- On failure (timeout, invalid JSON, schema mismatch): records `LLM_SUGGESTION_FAILED`, row stays in the manual queue. Ingestion does not fail.
- Suggestions land in `field_provenance` as `LLM_SUGGESTED`. A row with unreviewed LLM suggestions cannot be locked. Accepting flips provenance to `ANALYST_OVERRIDDEN`.
- Fully skipped if `GROQ_API_KEY` is absent.

**Sample data.**
Material `MAT-1004 "HSD Genset Fuel"` is included so the Groq path can demonstrate text-to-fuel-type inference. Material `MAT-9999 "Misc Office Supplies"` lands in spend-based with no fuel mapping — a natural Groq target for `spend_category` classification.

**Why this design.**
- The boundary between assist and fabricate is the boundary between text classification and numeric generation. I enforce it in code, not just in the prompt.
- Analyst-in-the-loop is non-negotiable for audit. No LLM output reaches a locked record without a human accept.
- Per-row caching prevents repeat paid calls when an analyst opens the same record multiple times.
- Graceful failure means a Groq outage cannot break ingestion or the analyst review queue.

**What would break in real deployment.**
- Prompt drift across Groq model versions — needs versioned prompts and regression evals.
- PII handling — material descriptions and travel records can contain employee names; production needs redaction.
- Rate-limit and cost monitoring at scale — current caching is per-row in DB; production needs a budget-enforcement layer.
- Multi-language input — prompt assumes English; production needs locale-aware prompting for German material descriptions, French expense reports, etc.
