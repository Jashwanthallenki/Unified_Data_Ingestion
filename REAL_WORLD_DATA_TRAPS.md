# Breathe ESG — Real-World Data Traps and Loopholes
## Research Document v2

---

## The Core Insight

The hardest problem in ESG data ingestion is not receiving data.
It is deciding whether the data actually represents real-world activity that should become emissions.

Every source has rows that look like emissions but are not.
Every source has rows that are emissions but look ambiguous.
Every source has rows where the right answer depends on context that is not in the file.

> **Not every row is activity.**
> **Not every activity becomes emissions.**
> **Not every missing value should be guessed.**
> **The hardest part is determining trust before analyst approval.**

This document captures every loophole identified across SAP fuel, SAP procurement, utility electricity, and corporate travel — what the trap is, why it exists, what goes wrong if you ignore it, and the decision made in the prototype to handle it.

---

## 1. SAP — Fuel (MB51 Goods Movements)

---

### Loophole 1.1 — Purchase does not equal consumption

**What happens:**
A company purchases 10,000 litres of diesel in January. It consumes 6,000 litres in January. The remaining 4,000 litres sit in the tank and are consumed in February.

If you calculate emissions from the purchase invoice, January is overstated by 4,000 litres. February has zero data even though 4,000 litres were burned.

**Why it exists:**
Finance systems record procurement events (money leaving the company). Operations systems record consumption events (fuel leaving the tank). These are different events at different times. Most ESG tools pull from finance data because it is easier to access — and they get this wrong.

**What goes wrong if ignored:**
Monthly emissions are wrong even if the annual total is approximately right. Quarterly reporting is unreliable. Any client comparing month-to-month trends is looking at noise, not signal.

**Decision:**
Source hierarchy enforced at ingest:
```
Tier 1: MB51 movement type 261/201 (goods issue = actual consumption)
Tier 2: Tank issue record or meter log
Tier 3: ME2M purchase invoice (weakest — fuel bought, not burned)
```
If both MB51 consumption and ME2M purchase records exist for the same material and period, MB51 is authoritative. ME2M records are tagged `superseded_by_consumption_data` and excluded from Scope 1 calculation. The source tier used is recorded in `field_provenance.source_tier` on every record.

---

### Loophole 1.2 — MB51 is not a fuel report — it is every goods movement

**What happens:**
MB51 (Material Document List) surfaces every goods movement in SAP — not just consumption. A single export contains goods receipts (diesel arriving at the warehouse), stock transfers (diesel moving from main tank to generator tank), reversals, scrapping, and goods issues (diesel actually consumed). All rows look identical in the CSV except for the movement type column.

**Why it exists:**
MB51 is a ledger report, not an operations report. SAP records every material event for inventory accounting purposes. It does not filter by "things that were burned."

**What goes wrong if ignored:**
Triple-counting fuel is the most common SAP ingest mistake:
```
Row 1: 101 — Diesel received at warehouse       (10,000 L)
Row 2: 311 — Diesel moved to generator tank      (10,000 L)
Row 3: 261 — Diesel issued to generator          (10,000 L)
```
A naive ingest treats all three as emissions: 30,000 L reported. Actual combustion: 10,000 L.

**Decision:**
Movement type filter is the first thing the SAP adapter applies — before normalisation, before unit conversion, before anything:

| Movement Type | Meaning | Action |
|---|---|---|
| 261 | Goods issue to cost centre | Include — consumption |
| 201 | Goods issue direct to cost centre | Include — consumption |
| 262 | Reversal of 261 | Net against original 261 |
| 101 | Goods receipt from supplier | Exclude silently |
| 301 | Plant-to-plant transfer | Exclude silently |
| 311 | Storage location transfer | Exclude silently |
| 551 | Scrapping / write-off | Flag for analyst review |
| Unknown | Not in known list | Flag `unknown_movement_type` |

Excluded rows are stored in the raw layer with `exclusion_reason`. They are not surfaced to the analyst by default but are accessible in the batch exclusion log for audit purposes.

---

### Loophole 1.3 — Reversals create phantom consumption

**What happens:**
SAP movement type 262 is the reversal of a 261. When fuel issued to a cost centre is returned or the transaction was posted in error, a 262 row appears in MB51 with a reference to the original document number.

```
261: Diesel issued to Generator 3    500 L    Doc 5000012345
262: Reversal                        200 L    Original Doc 5000012345
Net consumption:                     300 L
```

If you process each row independently:
- 261 generates emissions for 500 L
- 262 is either ignored (overcount by 200 L) or also generates emissions (overcount by 700 L)

**Why it exists:**
SAP corrects posting errors by creating reversal documents. This is normal operational practice — it is not unusual to see 5–10% of issue rows partially or fully reversed in a real export.

**What goes wrong if ignored:**
Overstatement of Scope 1 emissions. In a client with frequent operational corrections (large fleet, multiple generators, active corrections from field staff), this can be material.

**Decision:**
Reversal netting applied at adapter level. Group 261 and 262 rows by:
```
original_document_number + material_code + plant_code + posting_period
```
Net quantity = sum of 261 quantities − sum of 262 quantities.
Calculate emissions only on net quantity.

Edge case: a 262 references a document number that is not in the current batch (the original 261 was in a prior upload). Flag as `reversal_without_original`. The analyst must reconcile manually across batches. Do not auto-resolve — the prior batch may already be approved and locked.

---

### Loophole 1.4 — Movement type meaning can vary by client

**What happens:**
SAP allows companies to customise movement type behaviour. A movement type that means stock transfer for one company could represent a different operational process at another. Some companies create custom movement types (600+) for specific workflows.

**Why it exists:**
SAP is highly configurable. Enterprise clients implement it to match their operational processes, not to conform to a standard that ESG tools expect.

**What goes wrong if ignored:**
A movement type that means consumption at Company A might mean something else at Company B. Hard-coded exclusion rules could exclude real consumption events.

**Decision:**
Global movement type defaults applied. Custom movement type overrides will be supported as a client configuration option in future versions. For the prototype, unknown movement types are flagged `unknown_movement_type` and routed to analyst — never silently included or excluded.

---

### Loophole 1.5 — German column headers

**What happens:**
SAP exports column headers in the language of the user who ran the report. A German-speaking analyst at a German subsidiary produces:
```
Buchungsdatum, Werk, Materialnummer, Menge, Basismengeneinheit, Bewegungsart
```
An English-speaking analyst at the same company produces:
```
Posting Date, Plant, Material, Quantity, Base Unit of Measure, Movement Type
```
Both files contain the same data. Neither is wrong. A parser that expects English headers fails on the German export.

**Why it exists:**
SAP's multilingual UI is a feature, not a bug — but it creates the problem that the same export from the same system looks structurally different depending on who ran it.

**Decision:**
Header alias mapping applied at column detection. Every known SAP column name is registered in both English and German. Detection is done by comparing each header token against the alias table — not by position. Column order is never assumed. Mixed-language exports (some columns in German, some in English) are supported because each column is resolved independently.

---

### Loophole 1.6 — Mixed date and number formats in the same file

**What happens:**
SAP date format is set by the user's SAP locale. German installs: `31.01.2024`. US installs: `01/31/2024`. Some export configurations: `20240131`.

Number formatting also changes: European SAP uses `1.200,50` (period = thousands separator, comma = decimal). US SAP uses `1,200.50`. The same file can contain German dates and US numbers if the SAP user profile mixes settings.

A date `01.02.2024` is ambiguous — is it January 2 or February 1? Both formats can produce this string for different dates.

**What goes wrong if ignored:**
January and February emissions get swapped. A parser that assumes MM/DD reads European dates as wrong months.

**Decision:**
Date format detected from the first 10 data rows by testing candidate formats against each other for internal consistency. Ambiguous dates (where both interpretations are plausible given the detected format) are flagged as `ambiguous_date` and routed to analyst. Number format detected separately from first numeric row.

---

### Loophole 1.7 — SAP unit codes are not ISO units

**What happens:**
SAP uses internal unit of measure codes that look like ISO but are not always:
```
L   → litres              (correct)
KG  → kilograms           (correct)
TO  → metric tonnes       (looks like tons, is metric tonnes)
ST  → Stück / each        (German for piece — no energy content)
RM  → reams               (paper — no energy content)
GAL → US gallons          (3.785 L — not imperial gallons)
M3  → cubic metres        (correct)
MJ  → megajoules          (needs conversion to kWh: ÷ 3.6)
```

If fuel quantity is in KG and the emission factor is per litre (common for diesel), the emission calculation is wrong without a density conversion.

**Why it exists:**
SAP's unit system predates ISO standardisation and was built to support every possible material and industry. The unit code `ST` makes perfect sense for a bolt manufacturer. For an ESG tool ingesting fuel data, it is a warning that physical quantity is not available.

**Decision:**
Unit normalisation table applied before any emission factor is used. For KG → litres on liquid fuels: apply density (diesel: 0.832 kg/L, petrol: 0.745 kg/L, fuel oil: 0.850 kg/L). If density is required but not available in the reference table, flag `unit_density_required` and route to analyst. Unknown units flagged `unknown_unit` — never guessed.

---

### Loophole 1.8 — Vague fuel type descriptions

**What happens:**
Material descriptions like "Fuel", "Oil", "Industrial Fluid", "Combustibles" appear in real SAP exports. These descriptions may have been entered by procurement teams who did not anticipate that the description would drive emission factor selection.

**Why it exists:**
Procurement teams create materials for purchasing purposes, not for carbon accounting. A description that is good enough for a purchase order is not good enough for an emission factor lookup.

**What goes wrong if ignored:**
Wrong emission factor applied silently. Diesel EF ≠ LPG EF ≠ natural gas EF. Using the wrong one can over or understate emissions by 30–60%.

**Decision:**
Flag `ambiguous_fuel_type` when material description does not map to a known fuel type in the lookup table. LLM classification attempted only if confidence score ≥ 30 and the description contains enough context. LLM is not permitted to assign a numeric emission factor — it can only suggest a fuel type category for analyst confirmation.

---

## 2. SAP — Procurement (ME2M Purchase Orders)

---

### Loophole 2.1 — Purchase order does not equal delivery

**What happens:**
A PO is raised for 10,000 kg of steel. The supplier delivers 7,000 kg. The PO shows 10,000 kg. The goods receipt (GRN) shows 7,000 kg.

If emissions are calculated from the PO, 3,000 kg of steel that was never received generates phantom Scope 3 emissions.

**Why it exists:**
POs are often available in bulk exports (ME2M) because they are straightforward to run. GRNs require joining additional SAP tables. Procurement teams often send PO exports because they are easier — not because they are more accurate.

**Decision:**
Source hierarchy enforced for procurement:
```
Tier 1: Goods receipt (GRN) — delivery confirmed
Tier 2: Supplier invoice — financial confirmation
Tier 3: Purchase order only — intent, not delivery
```
PO-only records flagged `po_only_estimate` and capped at confidence 50. Final emissions not calculated until GRN or invoice confirms delivery.

---

### Loophole 2.2 — Same procurement event appears in multiple documents

**What happens:**
One procurement event flows through four SAP documents:
```
Purchase Order → Goods Receipt → Supplier Invoice → Payment Voucher
```
A client uploads an ME2M export (POs), a MIGO export (GRNs), and a MIRO export (invoices). All three contain the same procurement event. Without deduplication, emissions are counted three times.

**Decision:**
Deduplication key per procurement event:
```
vendor_id + po_number + material_code + quantity + goods_receipt_date
```
One emission record per unique procurement event. Additional document types for the same event are linked as supporting references, not separate emission records. Flag `procurement_duplicate_across_doc_types` if the same event appears in multiple uploads within the same batch.

---

### Loophole 2.3 — Capex vs opex vs energy — not all procurement is Category 1

**What happens:**
Not all purchased goods belong to Scope 3 Category 1. A client's procurement export contains:
```
Diesel (fuel)        → Scope 1 when consumed — route to fuel pipeline
Electricity bill     → Scope 2 — route to utility pipeline
Office laptop        → Scope 3 Category 2 (capital goods)
Packaging material   → Scope 3 Category 1 (purchased goods)
Consulting contract  → Scope 3 Category 1 (purchased services)
Financial penalty    → Not emissions-relevant
```

Routing all of these through the same procurement emission calculation produces wrong results.

**Decision:**
Material type classification applied at adapter level:

| Material type | Routing |
|---|---|
| Fuel / energy | Route to fuel or utility adapter — not generic procurement |
| Capital asset (machinery, vehicle, building) | Scope 3 Category 2 |
| Consumable goods / services | Scope 3 Category 1 |
| Financial instrument, deposit, penalty | Exclude — not an emission event |

---

### Loophole 2.4 — Spend-based method is sensitive to price, not activity

**What happens:**
Spend-based emission factor: `emissions = amount_spent × kg CO2e per £`

Same steel order, two scenarios:
```
Scenario A: 1,000 kg steel at £800     → 800 × EF
Scenario B: 1,000 kg steel at £1,400   → 1,400 × EF (supply chain disruption year)
```
The physical quantity is identical. The emissions reported are 75% higher in Scenario B due to price, not activity.

**Why it exists:**
Spend-based is used when physical quantities are unavailable. It is GHG Protocol compliant for Scope 3 Category 1 as a last resort. But it introduces price volatility noise that has nothing to do with actual emissions.

**Decision:**
Spend-based used only when no physical quantity is available. Always disclosed via `emission_method = "SPEND_BASED"` in field_provenance. Spend-based records capped at confidence 60. Spend amount cleaned before applying EF — exclude GST/VAT, late fees, deposits, penalties. Flag `spend_based_price_sensitivity` as an INFO-level flag on every spend-based record so analysts understand the limitation.

---

### Loophole 2.5 — Invoice amount includes charges unrelated to goods

**What happens:**
A supplier invoice includes:
```
Product line items:    £12,000
GST (18%):             £2,160
Freight charge:        £800
Late payment fee:      £150
Refundable deposit:    £500
Total due:             £15,610
```

If the full £15,610 is used for spend-based emission calculation, taxes and non-product charges inflate emissions by 30%.

**Decision:**
Spend amount extraction rule: use only line-item basic amount. Exclude GST/VAT, freight (classify separately under Scope 3 Category 4 if applicable), penalties, deposits. If the invoice does not itemise (lump total only), flag `invoice_not_itemised` and cap confidence at 40.

---

### Loophole 2.6 — Freight double-counting across Scope 3 categories

**What happens:**
Supplier A charges freight on their invoice for delivering steel. The client also tracks upstream freight separately under Scope 3 Category 4.

If both are counted, the freight emissions appear twice: once embedded in the product cost (Category 1) and once as explicit freight (Category 4).

**Decision:**
Check supplier emission factor source: if factor is product-level and explicitly includes upstream transport, do not separately classify freight invoices for that supplier under Category 4. Flag `freight_double_count_risk` if freight appears in both a product invoice and a separate freight invoice from the same supplier and period.

---

### Loophole 2.7 — Vendor-level classification is too broad

**What happens:**
A client submits invoices from a large distributor (Amazon Business, Grainger, W.W. Grainger). The vendor supplies office supplies, electronics, chemicals, cleaning products, and industrial consumables. Classifying by vendor name alone assigns the same emission factor to a box of paper and a drum of industrial solvent.

**Decision:**
Classify using material/line item description first. Use vendor category only as fallback when line item description is absent. Flag `vendor_level_classification_used` when fallback is applied.

---

## 3. Utility — Electricity

---

### Loophole 3.1 — Total amount due is not energy activity

**What happens:**
A utility bill total includes:
```
Energy charge (kWh usage):     £420
Demand charge (peak kW):       £85
Network standing charge:       £38
Climate levy:                  £22
VAT (5%):                      £28
Previous balance:              £60
Total due:                     £653
```

If £653 is used to calculate emissions via a spend-based electricity factor, the result is wrong. The emission factor applies to kWh consumed — not to total billing charges.

**Why it exists:**
Some portal exports do not surface the usage column clearly. Some facilities teams share the total from the bill rather than the usage figure. Some clients only have PDF bills (out of scope) and attempt to type in the total.

**Decision:**
`usage_kwh` is the only field used for electricity emissions. `total_amount` is stored for finance reconciliation only. If `usage_kwh` is absent and only `total_amount` is present, flag `missing_consumption_quantity` and cap confidence at 40. Do not apply an electricity spend-based factor — electricity has a direct kWh EF and spend-based introduces utility pricing noise.

---

### Loophole 3.2 — Estimated readings distort usage and create correction spikes

**What happens:**
Months 1–3: utility estimates 14,000 kWh each month (meter reader could not access site).
Month 4: actual read shows cumulative consumption was 52,000 kWh, not 42,000 kWh.
Utility issues a correction bill for +10,000 kWh adjustment.

If estimated readings are not flagged:
- Months 1–3 appear stable and correct
- Month 4 appears to spike dramatically
- The analyst cannot tell if Month 4 is a real operational change or a catch-up correction

**Why it exists:**
Meter readers cannot always access industrial sites. Utilities estimate based on prior history when they cannot read physically. This is standard and legal practice — but it creates artificial patterns in usage data.

**Decision:**
Flag `estimated_reading` on all rows where Notes/meter_read_type = "Estimated". Cap confidence at 70. Mark as `provisional` — subject to true-up. When a later actual read covers the same period, flag both records as `overlapping_billing_period`. Do not auto-resolve. Analyst must select which record supersedes the other. After confirmation, rejected record tagged `superseded_by_actual_reading`.

---

### Loophole 3.3 — Billing periods do not align with calendar months

**What happens:**
Utility billing cycle runs every 30 days from the connection date. A meter connected on March 15 generates bills that run March 15–April 13, April 14–May 12, and so on forever. The "January bill" covers December 28 – January 27.

Carbon reporting is always calendar-month based. If you sum bills by their billing date:
- January includes 4 days of December consumption
- March is missing the last 4 days (which appear in the April bill)
- Across a full year, the error accumulates to roughly one bill's worth of kWh

**Why it exists:**
Utilities set billing cycles based on meter read routes and logistics, not reporting calendars. This is not a data quality issue — it is correct data that does not align to the format carbon accounting requires.

**Decision:**
Pro-rate every billing record across calendar months at ingest:
```
daily_kwh = total_kwh / (billing_end - billing_start).days
For each calendar month M overlapping the period:
  days_in_M = days of billing period falling in month M
  kwh_for_M = daily_kwh × days_in_M
```
Store original `period_start` / `period_end` alongside the derived `calendar_month`. Do not discard billing period data — it is needed for audit and for detecting overlaps.

---

### Loophole 3.4 — Utility files can mix electricity and gas

**What happens:**
Dual-fuel accounts (electricity + gas from the same supplier) often export to a single CSV. Gas rows appear alongside electricity rows. Gas is measured in therms, CCF, or dekatherms — not kWh. A kWh-based electricity emission factor applied to a therm quantity is meaningless and produces a silent wrong number.

**Decision:**
Detect unit per row. Accept kWh rows for electricity processing. Reject therms/CCF/Mcf/dekatherm rows with a hard error: "Gas utility data detected — gas ingestion not yet supported in this module." Never silently apply a kWh emission factor to a gas quantity. Log rejected rows to the batch error log.

---

### Loophole 3.5 — Multiple meters at the same site create double-counting

**What happens:**
A factory has three electricity meters:
- Main building: MTR-001 (8,200 kWh/month)
- Production floor: MTR-002 (14,000 kWh/month)
- HVAC system: MTR-003 (6,400 kWh/month)

If the client uploads separate CSVs for each meter and the system creates one emission record per meter, site-level emissions are correct. But if the system or analyst later runs a site-level total by summing without knowing there are three meters, there is no double-count problem.

The problem occurs when:
- A client also provides a "total site" meter that includes MTR-001+002+003 aggregated by the utility
- OR when MTR-001 and a separate "campus total" meter both appear in the same file

**Decision:**
Unique utility account = `provider + account_number + meter_number + service_address`. Flag `possible_duplicate_site` if the same service_address appears under multiple meter numbers that could plausibly be nested (e.g. one campus meter and three building meters). Do not auto-aggregate. Route to analyst with a prompt: "Are these separate meters or does one meter include the others?"

---

### Loophole 3.6 — Utility rows may represent fees, not consumption

**What happens:**
Some utility portal exports include non-consumption rows:
```
Row type: Late payment charge    amount: £28    kWh: 0
Row type: Security deposit       amount: £200   kWh: 0
Row type: Service reinstatement  amount: £45    kWh: 0
```

These rows have zero kWh and should not generate emission records. But a naive parser that creates one record per row creates three zero-kWh records that clutter the review queue.

**Decision:**
Exclude rows where row_type indicates a fee, adjustment, deposit, or penalty. Log them to the exclusion audit trail with reason `non_consumption_row`. Flag `zero_kwh` on any row that passes the type filter but has zero usage — those are suspicious and may be a data error.

---

## 4. Corporate Travel

---

### Loophole 4.1 — Booking does not equal travel

**What happens:**
A flight is booked in March for a May trip. In April the trip is cancelled. The Concur booking system retains the record with status = CANCELLED. If the adapter reads all Concur records without checking status, a ghost flight appears in the emissions data.

**Why it matters:**
A cancelled flight that was never flown has zero real-world emissions. This is the most straightforward travel loophole but also the most consistently missed.

**Decision:**
Filter by segment status at the top of the travel adapter, before any other processing:
```
COMPLETED / FLOWN       → include
CANCELLED               → exclude silently, log to exclusion audit trail
REFUNDED                → exclude silently
NO_SHOW                 → exclude silently
```
Exclusion log accessible from batch detail page. Not surfaced to analyst by default.

---

### Loophole 4.2 — Expense row is not a travel segment

**What happens:**
Corporate expense systems contain:
```
Taxi reimbursement: £24
Meal claim: £45
Internet at hotel: £12
Travel adapter purchase: £8
```

All of these appear in expense export files alongside genuine travel events. None of them are travel segments with origin, destination, or distance. Some expense systems also include travel bookings made outside the corporate travel platform (personal bookings reimbursed).

**Decision:**
Require travel evidence. An Air emission record requires `origin_iata` + `destination_iata`. A Hotel record requires `check_in` + `check_out` + `location`. A Car record requires at minimum a `pickup_city`. Rows with only `amount` and `category = travel` and no routing data are flagged `expense_only_no_segment` and capped at confidence 40 (ground transport default applied).

---

### Loophole 4.3 — Flight distance may be missing, wrong, or computed from the wrong pair

**What happens:**
Concur sometimes provides a `distance_km` field. It is sometimes wrong (computed from city centroids, not airport coordinates). It is sometimes missing entirely. Airport codes are almost always present but occasionally contain errors (wrong IATA code, domestic vs international terminal codes).

For connecting flights, providing only the final origin and destination understates distance:
```
Direct:     HYD → LHR = 7,500 km
Connecting: HYD → DXB → LHR = 4,050 + 5,480 = 9,530 km (27% more)
```

**Decision:**
Distance source hierarchy:
```
Tier 1: Segment-level itinerary with IATA codes → haversine per segment, sum legs
Tier 2: Provided distance_km from Concur → use with flag `provider_distance_used`
Tier 3: City-level estimate from origin/destination city names
Tier 4: Cannot compute → flag `missing_distance`, do not estimate
```
LLM is explicitly forbidden from generating distance values. Great-circle distance underestimates actual routing by ~5–8% — documented and flagged on every record as `distance_estimated`.

---

### Loophole 4.4 — Connecting flights create multiple emission records for one journey

**What happens:**
Concur's Itinerary v4 API returns one Air segment per flight leg. A connecting journey produces multiple segments:
```
Segment 1: HYD → DXB    legId: LEG-001
Segment 2: DXB → LHR    legId: LEG-001
```

If each segment creates one emission record, the traveller appears to have made two independent journeys. Reports show two employees travelling when it was one employee on one trip.

**Why it exists:**
Airlines price and operate each leg independently. Concur stores each leg as a separate bookable unit. The API correctly returns two segments — the ESG system must interpret them as one journey.

**Decision:**
Group Air segments by `legId`. Create one emission record per leg. Sum distances across all segments within the leg. Apply dominant cabin class across the leg.

When `legId` is missing (some Concur configurations omit it): detect connections by matching arrival airport of segment N with departure airport of segment N+1, same employee, within 6-hour window. Flag `connection_detected_without_legid`.

---

### Loophole 4.5 — Round-trip bookings are stored inconsistently

**What happens:**
Travel platforms store return trips differently:
```
Format A: Two separate Air segments (LHR→JFK, JFK→LHR) under same trip_id
Format B: One record with trip_type = ROUND_TRIP and origin/destination only
Format C: Two separate trip bookings with no shared trip_id
```

Format A: correct — two emission records, one per leg.
Format B: if treated as one record, the return leg is missing from emissions.
Format C: risk of deduplication failure — two records that look independent but are the same person's round trip.

**Decision:**
Format A: process each segment independently — correct by default.
Format B: split into outbound and return emission records. Tag both as `round_trip_split`. Return leg inherits origin/destination reversed, same cabin class, same distance.
Format C: deduplication by `employee_id + departure_date + origin_iata + destination_iata + flight_number`. If the same key appears twice in a batch, flag `travel_duplicate`.

---

### Loophole 4.6 — Cabin class is missing or encoded in booking class codes

**What happens:**
Business class and economy class have fundamentally different per-passenger emissions due to seat floor-space allocation. First class on a long-haul flight is approximately 4× the emissions of economy on the same aircraft.

Concur stores cabin as either a human-readable field (`BUSINESS`, `COACH`) or as an IATA booking class code (`C`, `J`, `Y`, `M`, `B`). The booking class encoding is airline-specific and not standardised — `C` is business on most carriers but may differ on others.

**Why it matters:**
Missing cabin class for a VP who always flies business means understatement of emissions by 3–4× per flight. For a client with heavy executive travel, this is a material error.

**Decision:**
Cabin class normalisation table:
```
Y, B, M, H, Q, K, L, U, T, X, V → Economy
W, S (select carriers)            → Premium Economy
C, D, I, J, Z                    → Business
F, A, P                           → First
```
If cabin absent and booking class unrecognised: flag `unknown_cabin_class`, default to Economy (conservative — does not overstate), cap confidence at 65.

---

### Loophole 4.7 — Hotel booked nights may differ from stayed nights

**What happens:**
An employee books 4 nights at a hotel. They check out after 3 nights due to trip change. Concur's booking record shows 4 nights. The actual stayed nights are 3.

Emission factor is per room-night. Using booked nights overstates hotel emissions.

Conversely: a stay is extended by one night on-site. Concur booking shows 4 nights, actual stay was 5. Emissions are understated.

**Decision:**
Use check-out date minus check-in date as the room-nights calculation where actual checkout is recorded. Use booking confirmation dates only when actual checkout is absent. Flag `hotel_nights_estimated` when using booking dates. Do not include hotel records where check-out is entirely missing — flag `missing_checkout` and route to analyst.

---

### Loophole 4.8 — Room-nights vs employee-nights confusion

**What happens:**
Two employees share one hotel room for 3 nights. The emission factor is per room-night because electricity, heating, and water consumption are per room, not per person.

```
Correct:    1 room × 3 nights = 3 room-nights
Incorrect:  2 employees × 3 nights = 6 person-nights
```

Some expense systems record hotel stays per person, not per room. If the system treats each person's expense record as one room, emissions are doubled for every shared room.

**Decision:**
`room_nights` is the unit of calculation, not `person_nights`. Concur stores hotel bookings per booking (usually per room). If the record is an expense reimbursement (per-person hotel receipt), flag `group_hotel_room_count_missing` when the amount suggests a shared room but room count is not explicit.

---

### Loophole 4.9 — Hotel invoice includes charges unrelated to room occupancy

**What happens:**
A hotel invoice includes:
```
Room rate × 3 nights:    £450
Restaurant charges:      £120
Minibar:                 £35
Laundry:                 £28
Conference room hire:    £200
Airport transfer:        £45
VAT (20%):               £175
Total:                   £1,053
```

If the total is used for a spend-based hotel emission factor, non-accommodation charges inflate the result significantly. The conference room and airport transfer in particular have nothing to do with overnight stays.

**Decision:**
When room-night method is available, use it — do not use spend. When only spend is available, extract room rate only. If spend is a lump total with no itemisation, flag `hotel_spend_not_itemised`, cap confidence at 40, apply room rate estimate based on location average if LLM is triggered.

---

### Loophole 4.10 — Rental car fuel receipt and distance record for the same rental

**What happens:**
An employee rents a car for 3 days. They fill it up twice and submit fuel receipts as expenses. Concur also records the rental booking with a distance estimate.

If both the fuel receipts and the distance-based calculation are included, the rental car emissions are counted twice — once from fuel burned and once from estimated distance driven.

**Decision:**
Source hierarchy for rental car:
```
Tier 1: Actual fuel purchased quantity (fuel receipts) → fuel-based EF
Tier 2: Distance driven × car type EF
Tier 3: Rental invoice amount × transport spend EF
```
If fuel receipt and distance record both exist for the same rental (same employee + same dates + same vendor), use Tier 1 and suppress Tier 2. Flag `rental_car_fuel_receipt_used`. Never count both.

---

### Loophole 4.11 — Employee commuting mixed with business travel

**What happens:**
Scope 3 Category 6 is business travel. Scope 3 Category 7 is employee commuting. These are different categories with different calculation methodologies and different reporting requirements.

Some expense systems contain commuting reimbursements (employees claiming fuel or rail costs for daily home-to-office travel) alongside business trips. If all travel expenses are routed to Category 6, commuting is miscategorised.

**Decision:**
Classify by trip purpose from Concur trip_type or purpose field:
```
Purpose = business visit / conference / client meeting → Scope 3 Category 6
Purpose = office commute / home to work             → Scope 3 Category 7
Purpose absent                                       → flag `commute_vs_business_unverified`, default Category 6
```

---

## 5. LLM and AI-Assisted Suggestions

---

### Loophole 5.1 — Missing values should not automatically trigger LLM

**What happens:**
An LLM given only an ambiguous material code and no other context will hallucinate a plausible-sounding emission category. Given "MAT-004", it might say "This appears to be a petroleum-based material, likely diesel or heating oil" — confidently wrong.

LLM accuracy on ambiguous ESG classification depends entirely on having enough contextual input to constrain the output. Without context, it generates text that sounds correct and is not.

**Decision:**
LLM is only triggered when confidence score is 30–49 AND the record contains sufficient context:
- Raw row with partial description
- Partially normalised record
- Existing flags explaining what is missing
- Lookup table results (what was searched, what was not found)
- Surrounding rows from the same batch for context

LLM is never triggered on records scoring below 30 — those have failed normalisation and there is not enough context to constrain the output safely.

---

### Loophole 5.2 — LLM must not generate numeric values

**What happens:**
Asked to suggest a missing quantity, distance, or room-night count, an LLM will generate a plausible number. It will be stated with confidence. It will be wrong in ways that are not detectable without the original source data.

```
LLM given: "Diesel issued, Plant DE02, January 2024, quantity missing"
LLM output: "Based on typical plant consumption patterns, approximately 3,000–5,000 litres"
```

This number will end up in an emission calculation. It has no source. It cannot be audited. It is fabricated.

**Decision:**
LLM is explicitly forbidden from generating:
- Quantities (litres, kg, kWh, room-nights, distances)
- Document numbers, invoice numbers, reference IDs
- Dates or billing periods
- Emission factors or CO2e values

LLM may only:
- Classify descriptions into emission categories
- Suggest DEFRA spend category mappings
- Suggest fuel type from vague description text
- Explain why a field is missing and what source data would resolve it

Every LLM suggestion is tagged `LLM_SUGGESTED` in field_provenance and requires explicit analyst approval before the record can be locked. An LLM suggestion that is not reviewed cannot go to audit.

---

## 6. Summary — The Trust Ladder

Every record in the system sits at a position on this trust ladder. The adapter's job is to determine where. The analyst's job is to review anything below HIGH.

```
TRUST LEVEL    EXAMPLE                                        MAX CONFIDENCE
───────────────────────────────────────────────────────────────────────────
HIGH           MB51 261 row, L unit, known plant,            100
               known material, no flags

MEDIUM         MB51 261 row, KG unit (needs density),         75
               plant in lookup, estimated date

MEDIUM         Utility kWh, estimated reading, known site     70

LOW            ME2M PO only, no GRN, spend-based EF           50

LOW            Flight, unknown cabin class, distance           45
               estimated from city names

FAILED         Any row missing quantity + unit + date         <30
               → raw record only, no NormalizedActivity

───────────────────────────────────────────────────────────────────────────
SPECIAL        LLM suggested field present → cap at HIGH−10
               Spend-based method → cap at 60
               Source tier 3 → cap at 50
               PO-only procurement → cap at 50
```

The system's job is not to maximise the number of records that reach audit.
It is to ensure that every record that reaches audit deserves to be there.

---

## Architecture Statement

```
ERP / SAP / Utility Portal / Travel Platform
              ↓
    Source Detection and Raw Storage
    (every row preserved unchanged)
              ↓
    Rule-Based ESG Classification
    (movement type, segment status, document type)
              ↓
    Exclusion Layer
    (receipts, transfers, cancellations, fee rows)
              ↓
    Reversal and Deduplication Netting
    (261/262 pairs, procurement event keys, travel dedupe)
              ↓
    Source Hierarchy Enforcement
    (consumption > purchase, GRN > PO, stayed > booked)
              ↓
    Unit and Period Normalisation
    (SAP UoMs, billing pro-rata, density conversion)
              ↓
    Validation and Suspicion Detection
    (all flag rules applied per source)
              ↓
    Confidence Scoring and Method Selection
    (activity-based > distance-based > spend-based)
              ↓
    Optional LLM Suggestion
    (description classification only, score 30–49)
              ↓
    NormalizedActivity with full field provenance
              ↓
    Analyst Review Queue
    (everything below HIGH goes here)
              ↓
    Approval and Audit Lock
    (immutable once locked)
```