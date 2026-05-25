# Breathe ESG — Source Inputs & Research Evidence

This document records the real-world source formats I researched, the links I used as evidence, what the prototype uses, why the sample data is realistic, and what would break in a real deployment.

I removed screenshot dependencies from this version and kept the proof trail link-based so the documentation stays easy to maintain and review.

The goal of this file is to show that the ingestion design is based on realistic enterprise data shapes, not toy assumptions.

---

## Research Evidence Index

| Area | Link / Proof Source | Why I used it |
|---|---|---|
| SAP data models | https://towardsdatascience.com/my-first-steps-into-mastering-saps-data-models-4d20ad2485f2/ | To understand SAP’s table/module complexity and why direct SAP integration is not a simple CRUD/API problem. |
| SAP movement types | https://community.sap.com/t5/technology-blog-posts-by-members/sap-good-movement-types-list-of-sap-movement-types/ba-p/13551698 | To understand why movement type is critical before treating an SAP goods movement as ESG-relevant activity. |
| ESG platform architecture reference | https://github.com/adharsh277/Global-ESG-Intelligence-Platform | To compare a broader ESG analytics platform with my ingestion-control focused design. |
| SAP Concur Itinerary v4 docs | https://github.com/SAP-docs/preview.developer.concur.com/blob/main/src/api-reference/travel/itinerary-v4/v4.itinerary.md | To understand itinerary/travel API shapes, booking objects, date filters, and booking/segment concepts. |
| SAP Concur Developer Center | https://developer.concur.com/api-reference/ | To validate that enterprise travel platforms expose structured APIs and require scopes/auth. |
| SAP Concur itinerary guide | https://github.com/SAP-docs/preview.developer.concur.com/blob/main/src/api-guides/travel/get-itinerary.markdown | To understand how itinerary records are fetched and shaped around trips/bookings. |
| SAP Concur manual itinerary guide | https://github.com/SAP-docs/preview.developer.concur.com/blob/main/src/api-guides/travel/new-itinerary-manual.markdown | To understand travel segment types such as air, hotel, car, and rail. |
| SAP Concur direct connect hotel docs | https://developer.concur.com/api-reference/direct-connects/hotel-service/v4.hotel-service.html | To understand why hotel data is source-specific and not the same as generic travel spend. |
| SAP Concur direct connect ground transportation docs | https://developer.concur.com/api-reference/direct-connects/ground-transportation/v1.ground-transportation.html | To understand that ground transport has a separate data shape from flights and hotels. |
| Navan developer docs | https://developers.navan.com/ | To support the idea that enterprise travel data is API-shaped for large companies. |
| Green Button — Department of Energy | https://www.energy.gov/data/green-button | To support the utility data download/export assumption. |
| Green Button standard | https://www.greenbuttondata.org/ | To support structured utility usage data and machine-readable consumption exports. |
| Green Button sample files | https://green-button.github.io/samples/ | To understand realistic utility data structures and sample usage files. |
| Green Button Connect My Data | https://www.greenbuttonalliance.org/green-button-connect-my-data-cmd | To understand third-party access and utility customer data sharing. |
| Green Button utility bill data | https://www.greenbuttonalliance.org/utility-bill-data | To support billing-period and usage-summary thinking for utility ingestion. |
---

# 1. SAP — Fuel and Procurement

## Real-world format I researched

SAP ERP / S/4HANA can expose fuel and procurement data in multiple ways:

- **MB51** — Material Document List / goods movement export.
- **ME2M** — purchase documents by material.
- **SE16N/table exports** — direct table-style exports from SAP tables.
- **OData / SAP Gateway** — API-style integration.
- **IDoc / RFC / BAPI** — middleware or SAP-to-SAP integration mechanisms.

From my research, SAP is not a single clean API. It is a large ERP data model with module-specific tables, localized column names, custom fields, and client-specific configuration. That is why I chose a realistic onboarding input: exported CSV/Excel files.

## Links reviewed

| Link | What I used it for |
|---|---|
| https://towardsdatascience.com/my-first-steps-into-mastering-saps-data-models-4d20ad2485f2/ | Understanding SAP’s table/module complexity and why I should not model SAP as one simple ESG API. |
| https://community.sap.com/t5/technology-blog-posts-by-members/sap-good-movement-types-list-of-sap-movement-types/ba-p/13551698 | Understanding that movement type determines what kind of goods movement occurred. |
| https://github.com/adharsh277/Global-ESG-Intelligence-Platform | General ESG architecture comparison; helped separate analytics-layer thinking from ingestion-control thinking. |

## What I observed

SAP exports can include:

- goods receipts,
- goods issues,
- stock transfers,
- reversals,
- scrapping,
- procurement rows,
- German/localized headers,
- SAP-specific unit codes,
- internal plant codes,
- duplicate or reversed documents.

The main SAP risk is double-counting fuel by treating every goods movement as consumption.

Example:

- `101` means fuel arrived in inventory.
- `301` / `311` means fuel moved internally.
- `261` / `201` means fuel was issued/consumed.
- `262` can reverse an earlier issue.
- `551` can represent scrapping/write-off, which should not be automatically counted as combustion.

Only consumption-like rows should become Scope 1 fuel activity records.

## What the prototype uses

The prototype uses CSV/Excel upload through the ingestion console.

Implemented source shape:

- MB51-like fuel movement CSV.
- ME2M-like procurement CSV.
- Plant lookup CSV.
- Material lookup CSV.
- Unit mapping CSV.
- Movement type mapping CSV.
- Cost center lookup CSV.

API route:

```txt
/api/ingestion/sap/upload/
```

The SAP adapter handles:

- English and German column headers.
- Mixed date formats.
- European and US numeric formats.
- Unit normalization.
- Movement-type filtering.
- Plant lookup.
- Material lookup.
- Purchase vs consumption classification.
- Reversal and duplicate detection.
- Spend-based fallback for procurement records.

## Sample data

`fixtures/sap/`

| File | What it exercises |
|---|---|
| `sap_mb51_fuel_movements.csv` | Valid 261/201 consumption rows, 101 receipt exclusion, 311 transfer exclusion, 551 scrapping review case, 262 reversal, unknown movement type, duplicate document, suspicious high quantity, German headers, European numeric format, missing posting date, unknown plant, unknown material, units L/KG/M3/GAL. |
| `sap_me2m_procurement.csv` | Procurement rows with non-energy units such as ST/RM/EACH and mixed currencies for spend-based fallback. |
| `plant_lookup.csv` | Maps plant codes to facility names, countries, and cities. Missing plant codes trigger `UNKNOWN_PLANT_CODE`. |
| `material_lookup.csv` | Maps material codes/descriptions to fuel or procurement categories. |
| `unit_mapping.csv` | Maps SAP units to normalized units and conversion factors. |
| `movement_type_mapping.csv` | Maps movement types to ESG actions. |
| `cost_center_lookup.csv` | Maps cost centers to business units/regions. |

## Why this is realistic

This is realistic because SAP exports are often the first onboarding handoff from procurement or sustainability teams. The sample data includes the exact traps that would break naive ingestion:

- movement type ambiguity,
- purchase vs consumption,
- German headers,
- unit inconsistencies,
- internal plant codes,
- duplicate documents,
- reversals,
- unknown materials.

## What would break in real deployment

- Custom SAP Z-fields.
- Tenant-specific movement type behavior.
- Very large files requiring async processing.
- Real-time SAP sync.
- SAP S/4HANA-specific field variants.
- Missing or outdated plant/material lookup files.

---

# 2. Utility — Electricity

## Real-world format I researched

Electricity usage data reaches sustainability teams through:

- utility portal CSV/Excel exports,
- Green Button data exports,
- Green Button Connect My Data,
- PDF utility bills,
- utility APIs,
- EDI 867 feeds.

For this prototype, I focused on utility portal / Green Button-like CSV exports because that is a realistic structured handoff from a facilities team.

## Links reviewed

| Link | What I used it for |
|---|---|
| https://www.energy.gov/data/green-button | Understanding utility energy data download/export assumptions. |
| https://www.greenbuttondata.org/ | Understanding Green Button as structured utility usage data. |
| https://green-button.github.io/samples/ | Reviewing sample utility data files and realistic data structures. |
| https://www.greenbuttonalliance.org/green-button-connect-my-data-cmd | Understanding third-party utility data access and customer authorization. |
| https://www.greenbuttonalliance.org/utility-bill-data | Supporting billing-period and utility usage-summary thinking. |

## What I observed

Utility data is not just “bill amount.” It has ESG-specific quality problems:

- billing periods do not align with calendar months,
- estimated readings can distort trends,
- total amount can include taxes/fees/deposits,
- one site can have multiple meters,
- utility exports can mix electricity and gas,
- overlapping periods may happen after true-up/correction bills.

## What the prototype uses

CSV upload through:

```txt
/api/ingestion/utility/upload/
```

The utility adapter handles:

- meter/account to facility resolution,
- billing-period validation,
- calendar-month pro-rating,
- `usage_per_day` calculation,
- estimated-reading flags,
- overlapping billing periods,
- amount-only rows,
- non-consumption charge filtering,
- gas row rejection in electricity module,
- multiple meters per site.

## Sample data

`fixtures/utility/`

| File | What it exercises |
|---|---|
| `utility_electricity_export.csv` | Two meters at one site, estimated reading, Dec/Jan billing period, usage spike, 33-day period, 29-day period, zero kWh, negative kWh, tax-only row, late-fee-only row, amount-only row, overlapping billing periods, missing meter number, gas row with therms. |
| `meter_facility_lookup.csv` | Maps provider/account/meter to facility and country. Includes unmatched meter scenarios. |

## Why this is realistic

Real utility exports often come from billing portals, not clean ESG systems. A naive system would use only bill total or assign the entire bill to one month. This prototype instead preserves billing periods, calculates calendar allocations, flags estimates, and separates consumption from financial charges.

## What would break in real deployment

- Interval data at 15-minute/hourly level.
- Time-of-use breakdowns.
- Demand-charge methodology.
- PDF-only customers.
- Currency conversion for spend fallback.
- Weather-normalized analysis.
- Market-based Scope 2 evidence validation.

---

# 3. Corporate Travel

## Real-world format I researched

Corporate travel data usually comes from platforms such as:

- SAP Concur,
- Navan,
- Egencia / Amex GBT,
- travel agency APIs,
- expense systems,
- quarterly CSV drops.

For large enterprises, travel platforms expose structured APIs with trips, itineraries, bookings, segments, and expenses. That is why I modeled travel as an API sync rather than a file upload.

## Links reviewed

| Link | What I used it for |
|---|---|
| https://github.com/SAP-docs/preview.developer.concur.com/blob/main/src/api-reference/travel/itinerary-v4/v4.itinerary.md | Understanding SAP Concur itinerary/travel API shape and booking concepts. |
| https://developer.concur.com/api-reference/ | Validating that Concur APIs require scopes/auth and are organized into multiple enterprise APIs. |
| https://github.com/SAP-docs/preview.developer.concur.com/blob/main/src/api-guides/travel/get-itinerary.markdown | Understanding itinerary retrieval and travel sync behavior. |
| https://github.com/SAP-docs/preview.developer.concur.com/blob/main/src/api-guides/travel/new-itinerary-manual.markdown | Understanding manual itinerary and segment-type thinking. |
| https://developer.concur.com/api-reference/direct-connects/hotel-service/v4.hotel-service.html | Understanding that hotel records have their own service/data shape. |
| https://developer.concur.com/api-reference/direct-connects/ground-transportation/v1.ground-transportation.html | Understanding that ground transportation has a separate service/data shape. |
| https://developers.navan.com/ | Supporting the general API-based travel ingestion choice beyond Concur. |

## What I observed

Travel data has many traps:

- booking does not always mean travel happened,
- cancelled/refunded bookings should not produce emissions,
- flight distance may be missing,
- flight legs/connections can be double-counted,
- cabin class may be missing or inconsistent,
- hotel booking nights may not equal stayed nights,
- expense-only rows may not contain actual travel evidence,
- bundled packages may mix hotel/flight/transport,
- rideshare rows often only have amount, not distance.

## What the prototype uses

A Django-hosted mock API:

```txt
/api/mock-travel/sync/
```

The ingestion endpoint:

```txt
/api/ingestion/travel-sync/
```

calls this mock API as if it were an external travel platform.

The travel adapter handles:

- flight/hotel/car/rail/expense segment types,
- cancellation/refund/void exclusion,
- leg grouping,
- cabin class mapping,
- distance hierarchy,
- hotel room-night calculation,
- bundled package flagging,
- expense-only exclusion,
- rideshare low-confidence fallback.

## Sample data

`fixtures/travel/mock_response.json`

Includes:

- round-trip flight,
- connecting flight with same `leg_id`,
- codeshare duplicate,
- cancelled flight,
- refunded booking,
- voided booking,
- flight missing distance but with airport codes,
- flight missing airport codes,
- valid hotel stay,
- hotel missing checkout,
- same-day hotel stay,
- bundled hotel/travel package,
- car rental same city,
- car rental different cities,
- rideshare amount-only row,
- expense-only row,
- economy/business/first/unknown cabin classes.

`fixtures/lookups/airport.csv`

Includes IATA airport codes with latitude, longitude, and country.

## Why this is realistic

The SAP Concur and Navan documentation show that travel platforms expose structured APIs and use concepts such as trips, bookings, segments, dates, and authorization scopes. The sample data mirrors realistic travel issues: cancelled trips, missing distances, multiple segments, cabin classes, and hotel stay logic.

## What would break in real deployment

- OAuth setup.
- Per-tenant API credentials.
- Refresh-token storage.
- Pagination across large date ranges.
- Provider-specific schema drift.
- Rate limits and retry handling.
- PII handling for employee travel data.

---

# 4. Groq LLM — Optional Reasoning Layer

## Real-world format I researched

LLMs are useful in ESG ingestion when the issue is text interpretation, not numeric truth.

Examples:

- classifying ambiguous material descriptions,
- suggesting spend categories,
- explaining low confidence,
- suggesting analyst follow-up questions,
- interpreting messy descriptions.

The important boundary is that LLMs should not generate audit-critical numeric data.

## Links reviewed

| Link | What I used it for |
|---|---|
| https://console.groq.com/docs/structured-outputs | Designing structured JSON suggestions instead of free-form LLM text. |
| https://console.groq.com/docs/api-reference | Understanding backend Groq API usage and request/response shape. |
| https://console.groq.com/docs/overview | Understanding integration setup and API-key-based backend usage. |

## What the prototype uses

Groq is called from the backend only when:

- confidence is LOW,
- deterministic mapping failed,
- rule-based lookup failed,
- the row still has useful text context.

The service receives:

- source type,
- raw payload,
- partially normalized record,
- missing fields,
- validation flags,
- lookup context.

Groq returns structured JSON suggestions.

Example:

```json
{
  "suggestions": [
    {
      "field": "activity_subtype",
      "suggested_value": "DIESEL",
      "confidence": 0.72,
      "reason": "Material description contains HSD and genset fuel.",
      "method": "LLM_SUGGESTED"
    }
  ]
}
```

## Why this is realistic

This mirrors how I would use an LLM safely in production: not as a source of truth, but as a suggestion layer over evidence.

Groq can suggest text classifications, but it cannot invent:

- quantities,
- dates,
- document numbers,
- bill numbers,
- kWh,
- flight distances,
- hotel nights,
- audit references.

## What would break in real deployment

- model/version drift,
- prompt regression,
- cost control,
- rate limits,
- PII handling,
- multilingual source descriptions,
- need for evaluation tests.

---

# 5. ESG Platform Architecture Reference

## Reference reviewed

| Link | What I used it for |
|---|---|
| https://github.com/adharsh277/Global-ESG-Intelligence-Platform | Understanding broader ESG platform architecture and comparing it with my more focused ingestion-control system. |

## What I observed

A broader ESG analytics system usually focuses on:

```txt
multi-source ESG data
→ ingestion
→ processing
→ analytics
→ dashboards
```

My prototype sits one layer earlier:

```txt
messy client source data
→ raw storage
→ eligibility filtering
→ normalization
→ validation
→ analyst review
→ audit lock
```

The focus is not only analytics. The focus is making incoming ESG activity data trustworthy before it reaches analytics or audit.

---

# 6. Summary — Why These Source Choices

The prototype demonstrates that the ingestion-control logic is the hard part.

The source decisions are:

1. SAP uses CSV/Excel because enterprise onboarding often starts with exported SAP reports.
2. Utility uses CSV because facilities teams commonly download structured utility portal exports.
3. Travel uses a mocked API because enterprise travel platforms expose structured APIs.
4. Groq is used only for controlled text reasoning, not numeric generation.
5. All sources normalize into the same `NormalizedActivity` model.

The key research-driven conclusion is:

```txt
Not every row is ESG activity.
Not every purchase is consumption.
Not every bill amount is energy usage.
Not every booking is travel.
Not every missing value should be guessed.
```

That is why the prototype focuses on raw record preservation, source-specific rules, validation, confidence scoring, provenance, and analyst review.
