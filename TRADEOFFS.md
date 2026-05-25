# Breathe ESG — Tradeoffs
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
