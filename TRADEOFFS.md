# Breathe ESG — Tradeoffs

What I deliberately did not build, and why those choices made sense for a 4-day prototype that needs to demonstrate ingestion judgment, not feature coverage.

---

## 1. Real integrations vs realistic mock inputs

**What I did not build:**
Live SAP OData / BAPI / IDoc connections. Live utility-portal APIs. Utility PDF bill OCR. Real Concur / Navan OAuth integration.

**What I built instead:**
CSV upload for SAP and utility (that's how real onboarding handoffs arrive). A Django-hosted mock endpoint at `/api/mock-travel/sync/` returning Concur/Navan-shaped JSON, including cancelled / refunded / voided / codeshare / missing-distance / bundled-package edge cases.

**Why:**
Real integrations need credentials, sandboxes, security review, and tenant-specific configuration. That work is real but it does not exercise the data-trust judgment that's actually being graded. I'd rather demonstrate that the pipeline handles messy data correctly than that I can wire up OAuth.

**What this still proves:**
Movement-type filtering, German/English header detection, billing-period pro-rata, estimated-reading handling, cancellation filtering, hotel room-night math, leg grouping, source-hierarchy selection, deduplication, validation, confidence scoring, field provenance, analyst review, audit lock. The transport layer is the only piece that's mocked.

**What changes in production:**
The file uploader (or mock travel endpoint) is replaced by a real connector with auth, pagination, retries, and schema-drift handling. `NormalizedActivity` and the analyst workflow do not change.

---

## 2. Advanced emission factor engine vs ingestion correctness

**What I did not build:**
Full DEFRA / EPA / IEA factor sets. Versioned country/grid-specific electricity factors. Market-based Scope 2 from REC certificates. Currency-specific spend factors. Supplier-specific Scope 3. Factor uncertainty intervals.

**What I built instead:**
A small `EmissionFactorMapping` table with illustrative DEFRA-2024-style factors for diesel, petrol, natural gas, electricity (location-based grid average + a few country variants), flights by cabin × haul, hotel nights, car, rail, and spend-based fallback. Each factor row carries `source` + `version`. The active version is snapshotted onto the `IngestionBatch` at ingestion time.

**Why:**
The build prompt's own framing is that the hard part is messy data, not carbon math. A production factor engine is a multi-month workstream — curation, vintage management, jurisdiction matrix, supplier-specific factors, audit trails. Spending the prototype budget on that means cutting ingestion logic, which is exactly the wrong trade.

**What this means for `co2e_kg`:**
Values are computed and stored with `emission_factor_source` populated, but the magnitudes are illustrative. They show the pipeline working end-to-end; they aren't audit-grade footprint numbers and I don't want to pretend they are.

**What changes in production:**
`services/normalization.py` keeps selecting method and unit. The factor lookup gains jurisdiction + supplier + vintage dimensions, probably backed by an external factor service.

---

## 3. Authentication and RBAC

**What I did not build:**
Login, password reset, SSO, user invitations, role assignment, per-tenant user pools, access audit logs.

**What I built instead:**
One seeded tenant ("Demo Enterprise Client") and one implicit analyst user used as the reviewer on every `ReviewLog`. The `Tenant` foreign key is on every domain row, so multi-tenant scoping is a deploy concern, not a schema refactor.

**Why:**
Auth and RBAC are real production work. They do not exercise the ingestion / provenance / review judgment this prototype is meant to demonstrate. I'd rather ship a system that handles messy SAP data correctly than a system that logs me in correctly.

**What changes in production:**
SSO + RBAC layered on the existing tenant model. Locked-row unlock gated on admin role.

---

## 4. Utility PDF bill OCR

**What I did not build:**
OCR or layout extraction for scanned utility bill PDFs.

**What I built instead:**
CSV ingestion for utility-portal exports (account, meter, billing period, usage_kwh, demand, charges, reading type).

**Why:**
PDF utility bill extraction is its own domain — OCR engines, per-utility templates, layout parsers, LLM-assisted extraction with verification. Half-built OCR is worse than no OCR: it produces wrong-looking values that look right. The ESG question is what to do with the structured data, which is what I focused on.

**What changes in production:**
A document-processing pipeline upstream of the existing utility adapter. Same `NormalizedActivity` model after.

---

## 5. Real Concur / Navan OAuth

**What I did not build:**
OAuth 2.0 handshake, refresh-token rotation, scope management, per-tenant credential storage, real provider rate-limit handling.

**What I built instead:**
A mock endpoint `/api/mock-travel/sync/` returning Concur/Navan-shaped JSON. The travel ingestion flow calls it the same way it would call a real provider.

**Why:**
The judgment under test is whether the adapter handles cancellations, leg grouping, cabin classes, codeshare duplicates, distance fallbacks, hotel room-night math, and bundled packages — not whether I can complete an OAuth dance.

**What changes in production:**
`/api/mock-travel/` is deleted. The travel adapter's HTTP client points at the real provider with auth + pagination. Downstream logic stays put.

---

## 6. Full SAP procurement universe

**What I did not build:**
SAP FI, CO, MIRO documents. Custom Z-fields. S/4 HANA-renamed field variants. Production confirmation chains. SAP fleet-management modules.

**What I built instead:**
MB51 (goods movements — primary fuel source) and ME2M (procurement — spend-based fallback). The adapter is column-mapping driven, so new SAP shapes become new mappings, not new models.

**Why:**
MB51 and ME2M cover the bulk of what an onboarding sustainability team has access to. The long tail of SAP modules adds breadth, not depth.

---

## 7. Market-based Scope 2 evidence validation

**What I did not build:**
REC / GO / I-REC certificate validation, renewable contract parsing, certificate retirement tracking, market-based factor application from verified evidence.

**What I built instead:**
Location-based Scope 2 by default. If a row claims market-based but evidence is absent, I flag `MARKET_BASED_SCOPE2_EVIDENCE_MISSING` and route to analyst review.

**Why:**
Market-based Scope 2 is evidence-heavy and regulated. Half-implemented certificate validation creates false confidence around renewable claims, which is worse than not implementing it. Flagging it explicitly is honest.

**What changes in production:**
A certificate-management subsystem for REC tracking + retirement + period matching.

---

## 8. Groq is not allowed to generate numerics — permanent, not provisional

**What I deliberately restricted:**
Groq cannot suggest values for quantity, distance, usage_kwh, room_nights, dates, document numbers, ticket numbers, invoice numbers, bill numbers, or amounts. The response parser drops any suggestion for a forbidden field and records a note.

**What Groq can do:**
Classify ambiguous material descriptions, suggest spend categories, judge ESG relevance, explain low confidence, suggest analyst follow-up questions. All output lands in `field_provenance` as `LLM_SUGGESTED` and must be explicitly accepted by an analyst before the row can be locked.

**Why:**
Numeric hallucination is the highest-impact failure mode in an ESG system. A hallucinated kWh is indistinguishable from a real one in downstream reports. The dividing line between "assist" and "fabricate" is exactly the line between text classification and numeric generation. This is not a prototype limitation — it's a permanent design constraint.

---

## 9. UI polish, animations, design system

**What I did not build:**
Custom design system, animations, dark mode, deep accessibility audit, mobile-responsive beyond what Tailwind gives for free.

**What I built instead:**
Plain functional UI with Tailwind. Color-coded badges for the high-signal states the analyst needs to spot at a glance: `SPEND_BASED` (amber), `ESTIMATED_READING` (blue), `LLM_SUGGESTED` (purple), `LOCKED` (indigo), `SUSPICIOUS_*` (rose). Summary cards link directly to filtered table views.

**Why:**
The prototype demonstrates ingestion + review logic. Visual polish does not move that needle.

---

## 10. Background job processing

**What I did not build:**
Celery / RQ / Django-Q queue for async file processing.

**What I built instead:**
Synchronous processing inside the upload endpoint. The batch summary is the response.

**Why:**
For the prototype's row counts (tens to low thousands), synchronous works. Adding workers, queues, and Redis adds deployment complexity without exercising any new judgment.

**What changes in production:**
Queue-based ingestion. Upload endpoint creates an `IngestionBatch` in `PROCESSING` status and returns immediately; a worker drains the queue and updates progress.
