# Breathe ESG — Decisions Log

The decisions I made while building this prototype, in the order I made them. Each one is something I'd expect to be asked "why?" about; I've answered that question in line.

---

## 1. SAP — CSV upload instead of IDoc / OData / BAPI

**Decision:**
I ingest SAP fuel and procurement data through CSV/Excel upload. The expected files are MB51-like goods movement exports and ME2M-like procurement exports.

**Why I chose this:**
A live SAP integration needs client credentials, SAP-side configuration, network access, security approval, module permissions, and tenant-specific field mappings. That work is real, but it does not exercise the judgment this prototype is meant to demonstrate.

In real onboarding, the first artifact a sustainability or procurement team shares is usually an exported MB51 spreadsheet. I built for that handoff. A future OData/RFC connector replaces the file uploader without changing the normalized model or analyst workflow.

---

## 2. SAP subset — MB51 + ME2M only

**Decision:**
I handle two SAP export shapes:

- MB51-style material movements — the primary fuel-activity source.
- ME2M-style procurement — a spend-based fallback when no consumption record exists.

**Why I chose this:**
Fuel emissions live in SAP MM movements. That is where goods issues, transfers, receipts, reversals, and scrap appear. Procurement data is one step removed from consumption — a company can buy 10,000 L of diesel and burn 6,000 L this month — so I treat it as a weaker source.

**What I left out:**
I did not cover SAP FI, CO, MIRO, production confirmations, fleet modules, custom Z-fields, or S/4 HANA-specific variants. Those add breadth, not depth. The adapter is structured so new export shapes become new column mappings, not new models.

---

## 3. SAP — movement type filtering before ESG classification

**Decision:**
No SAP row becomes an ESG activity until it passes through `MovementTypeMapping`:

- `261` / `201` → fuel consumption, ESG-relevant.
- `101` → goods receipt → `fuel_purchased`, not direct Scope 1.
- `301` / `311` → stock transfer → excluded from emissions.
- `551` → scrapping → routed to analyst review.
- `262` → reversal → linked to the original document and netted.
- Unknown → routed to analyst review as `UNSUPPORTED_MOVEMENT_TYPE`.

**Why I chose this:**
MB51 contains every goods movement, not just consumption. If I summed quantity per material across the file, I would double- or triple-count fuel: once when it arrives, once when it transfers, once when it is consumed. Movement-type filtering is the main SAP-specific judgment in this prototype, and it is where naive ingesters fail.

**Why the mapping is global, not tenant-scoped:**
Standard SAP movement type semantics are defined by SAP. A `311` means storage-location transfer regardless of which customer is running the system. I left the model extensible if a customer ever uses a custom movement type.

---

## 4. Fuel purchase is not fuel consumption

**Decision:**
Goods receipts and purchase invoices become `fuel_purchased` or `inventory_increase`, never direct Scope 1 emissions. Goods issues, tank issues, and consumption logs become `fuel_consumed`.

**Why I chose this:**
Fuel bought in one month and burned in another would skew both periods if I counted the purchase as the emission. The source hierarchy I use:

1. Actual consumption / meter log.
2. Goods issue / tank issue.
3. Purchase invoice (weakest; used only when nothing better exists).

Purchase records still earn their place in the dashboard for reconciliation, but they cannot become locked emissions evidence on their own.

---

## 5. Utility — CSV upload instead of PDF OCR or live API

**Decision:**
I ingest utility electricity data through CSV upload, modelled on a utility-portal / Green Button-style export.

**Why I chose this:**
Facilities teams download structured exports from utility portals; that is the realistic onboarding input. PDF utility bill OCR is its own domain — OCR, layout parsing, per-utility templates, verification. Live utility API integrations need per-provider contracts and credentials.

I focused on what comes after the data is structured: billing periods that don't align to months, estimated readings, multiple meters per site, amount-only rows, and non-consumption charges. That is the ESG-quality problem.

---

## 6. Utility — pro-rate billing periods across calendar months

**Decision:**
A bill that spans two calendar months produces two `NormalizedActivity` rows, one per month, with `usage_kwh` scaled by `days_in_month / total_days`.

Example:

```
Billing period: 2024-12-28 → 2025-01-27 (31 days, 12,500 kWh)
  → December 2024 record: 4 days, 1,613 kWh
  → January 2025 record:  27 days, 10,887 kWh
```

**Why I chose this:**
ESG reporting is monthly or quarterly. Bill cycles align to meter-read dates, not calendar months. Treating a Dec 28 → Jan 27 bill as a single January row understates December's footprint and overstates January's. Pro-rata is the documented industry fix.

I also store `usage_per_day` on every row so spike detection compares like-for-like — a 35-day bill is not "suspicious" just because it has more total kWh than a 28-day bill.

**Limit I accept:**
Pro-rata assumes uniform daily usage over the billing period. For facilities with strong weekday/weekend or weather variation that assumption is wrong, but without interval data it is the best available.

---

## 7. Utility — estimated readings stay in the pipeline, capped at confidence 70

**Decision:**
When `reading_type = estimated`, the row is normalized but marked `is_estimate = true`, flagged `ESTIMATED_READING`, and confidence is capped at 70 (MEDIUM band). If a later actual bill overlaps the same period, both rows are kept and `POSSIBLE_AMENDED_BILL` raises for analyst reconciliation.

**Why I chose this:**
Dropping estimates loses information. Treating estimates the same as actuals lies about quality. Capping confidence + badging the row gives the analyst what they need to decide.

---

## 8. Utility — gas rows are rejected, not silently converted

**Decision:**
Rows with units of `therms`, `CCF`, or `m3 gas` arriving via the electricity import are rejected with `GAS_UTILITY_DATA_DETECTED` and never produce a normalized activity.

**Why I chose this:**
Applying an electricity emission factor to a therm value is wrong by roughly an order of magnitude. Of all the failure modes I considered, silent unit confusion is the most expensive — it produces a plausible-looking number that is dangerously wrong. The safe path is to reject + flag and let the analyst re-route the file.

---

## 9. Travel — mocked Concur/Navan API instead of real OAuth

**Decision:**
The backend exposes `GET /api/mock-travel/sync/?start_date=&end_date=` returning JSON shaped like a real Concur/Navan sync response. The travel ingestion endpoint calls this internally.

**Why I chose this:**
Concur and Navan both expose structured trip/segment records through authenticated APIs. For a 4-day prototype, the OAuth handshake, sandbox provisioning, and per-tenant credential storage would eat the whole timeline. A mock that matches the real response shape lets the *ingestion logic* be what's under test.

The travel adapter that consumes the mock would consume the real API with auth + pagination layered on. Replacing the mock is an isolated change.

---

## 10. Travel — distance must come from source data or deterministic rules, never the LLM

**Decision:**
Flight distance is resolved in this priority order:

1. Distance field on the source record.
2. Haversine great-circle distance from `AirportLookup` lat/lon for origin / destination IATA codes (flagged `DISTANCE_ESTIMATED`).
3. Missing → `MISSING_FLIGHT_DISTANCE`, routed to analyst review.

The LLM is not allowed to infer distance from text.

**Why I chose this:**
Distances feed directly into emissions. An LLM-invented distance is indistinguishable from a real one in downstream reports but produces audit liability. The same boundary applies to quantities, dates, document numbers, and amounts. Numerics come from rules; text inference comes from the LLM, only when explicitly accepted by an analyst.

---

## 11. Confidence as a 100-point banded score, not a black-box ML number

**Decision:**
Every activity starts at 100. Each validation flag deducts a fixed amount. The final score bands into HIGH (80+) / MEDIUM (50–79) / LOW (30–49, LLM-eligible) / FAILED (<30).

**Why I chose this:**
The dashboard needs to sort by quality, the audit lock can be gated on a threshold, and an analyst can trace any score back to the flags that produced it. An ML-learned score would be more accurate in theory but unexplainable — and explainability is the whole point of analyst review.

Every deduction in the table is documented, every flag has a severity, and every score is reconstructible from `flags` alone.

---

## 12. Groq is text-only and analyst-gated, with hard guardrails on numerics

**Decision:**
Groq is invoked only when confidence falls into LOW (30–49) and deterministic rules have failed. The service is constrained:

- **Allowed fields:** activity_subtype, scope_category, spend_category, is_esg_relevant, review_explanation, client_followup.
- **Forbidden fields** (filtered out of the response in code, not just in the prompt): quantity, distance_km, usage_kwh, room_nights, dates, document_number, ticket_number, confirmation_number, invoice_number, bill_number, amount.

Every suggestion lands in `field_provenance` as `LLM_SUGGESTED`. An activity with unreviewed LLM suggestions cannot be locked. Accepting a suggestion flips its provenance to `ANALYST_OVERRIDDEN`.

**Why I chose this:**
The boundary between "assist" and "fabricate" is exactly the boundary between text classification and numeric generation. LLMs reason well over text and hallucinate aggressively over numerics. I enforce that boundary in code (response parser drops forbidden fields with a note), not just in the prompt. Per-row caching prevents repeat paid calls when an analyst opens the same record multiple times. Graceful failure (JSON parse error / timeout / missing key) records a `LLM_SUGGESTION_FAILED` validation issue and keeps the row in the manual queue.

---

## 13. Audit lock is a separate step from approval, with a frozen snapshot

**Decision:**
Approval and lock are distinct operations. Locking writes a JSON snapshot of `field_provenance`, flags, eligibility decision, source hierarchy rank, emission factor + version, and active validation issues onto the activity. The API rejects mutations on locked rows.

**Why I chose this:**
GHG audits require record-level immutability and a reconstructible explanation. "We can recompute it" and "we recorded what we computed" are not the same thing. If a lookup version is bumped six months after lock, the locked row must still answer "what was this number based on?" — and the snapshot is the answer.

---

## 14. No authentication or RBAC

**Decision:**
One seeded tenant ("Demo Enterprise Client"). One implicit analyst user. No login, no SSO, no role assignment, no per-tenant user pool. The `Tenant` foreign key exists on every domain row.

**Why I chose this:**
Authentication is real work but it doesn't prove the data-trust judgment this prototype is meant to demonstrate. I built tenant scoping into the schema so multi-tenant deployment is a deploy-config change, not a refactor. Production adds SSO and RBAC on top of the existing model.

---

## What I would ask the PM if I could

These are the ambiguities I resolved by judgment call. In a real engagement I'd lock each with the PM before shipping:

1. **Reversal window.** How far back can a `262` reversal link to a `261`? I default to "same batch or last 90 days". Production probably needs longer.
2. **Hotel factor by country.** Hotel-night emissions vary widely by country and brand. I use one global factor; production needs country-level resolution.
3. **Locked-row unlock policy.** Self-service with audit, or admin-only? I implement reject + log; no unlock path.
4. **Reporting period.** Calendar year, fiscal year, or rolling? I default to calendar, which drives the utility pro-rata.
5. **Multi-currency consolidation.** A multi-region tenant in EUR + USD + INR — does the dashboard report a single converted figure, or split by currency? I keep currency per-row.
