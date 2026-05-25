# Breathe ESG — Prototype

ESG ingestion-control and analyst-review system for converting messy SAP, utility, and travel data into normalized, confidence-scored, provenance-tracked activity records before audit.

This is not a generic CRUD dashboard. The prototype focuses on the real data-trust problem in ESG workflows: deciding which source rows are relevant, which rows are incomplete or suspicious, which values were directly provided or derived, and which records an analyst can approve before audit lock.

The app includes:

- an ingestion console for SAP, utility, and travel inputs,
- source-specific normalization and validation,
- raw source record preservation,
- duplicate detection and reconciliation controls,
- confidence scoring and validation flags,
- optional Groq suggestions for low-confidence rows,
- an analyst review dashboard,
- approval and audit-lock workflow.

Single seeded tenant: `Demo Enterprise Client`.

The app is intentionally unauthenticated for prototype simplicity. This is a deliberate scope choice and is explained in [TRADEOFFS.md](TRADEOFFS.md).

---

## Live Demo

Add deployed app URL here:

```txt
https://<your-render-app>.onrender.com
```

Demo tenant:

```txt
Demo Enterprise Client
```

Seeded Django admin users:

```txt
admin / admin
analyst / analyst
```

The main app UI is unauthenticated. The seeded users are mainly for Django admin and review-log attribution.

---

## Documentation

I have kept the design rationale in separate documents so the project is easy to review beyond just the deployed app. These docs explain how I approached the assignment, how I modeled the data, what decisions I made, what I intentionally left out, and how I handled realistic source-specific edge cases.

| Document | What it explains |
|---|---|
| [APPROACH.md](APPROACH.md) | My end-to-end approach: problem understanding, architecture, ingestion-review flow, Groq usage, tenant design, and deployment approach. |
| [MODEL.md](MODEL.md) | The core data model: tenants, ingestion batches, raw records, normalized activities, validation issues, provenance, confidence scoring, review logs, and audit lock. |
| [DECISIONS.md](DECISIONS.md) | The key design decisions I made and the reasoning behind each one. |
| [TRADEOFFS.md](TRADEOFFS.md) | The things I deliberately did not build, why I left them out, and what I would do in production. |
| [SOURCES.md](SOURCES.md) | The research links and source-shape evidence I used for SAP, utility data, travel systems, Groq, and ESG platform design. |
| [REAL_WORLD_DATA_TRAPS.md](REAL_WORLD_DATA_TRAPS.md) | The real-world ingestion traps I identified, such as purchase vs consumption, estimated readings, cancelled bookings, duplicates, reversals, and LLM numeric hallucination. |
| [PLAN.md](PLAN.md) | The build plan, shipped scope, milestones, and future improvements. |

---

## Prototype Scope and Intentional Limitations

I made a few deliberate scope choices to keep the prototype focused on the assignment’s core evaluation areas: data model quality, realistic source handling, analyst review, and tradeoff clarity.

| Area | Prototype choice | Why I chose it |
|---|---|---|
| Product structure | Ingestion and review are included in one application | This makes the demo easier to follow: upload data, see how it normalizes, then review the resulting records in the same flow. |
| Frontend deployment | React is built as an SPA and served by Django through WhiteNoise | This gives reviewers one deployed URL and avoids CORS/frontend-backend environment issues during review. |
| External integrations | SAP and utility use realistic CSV uploads; travel uses a mocked Concur/Navan-like API | Real SAP, utility, and travel integrations need credentials, OAuth, sandbox access, and client-specific setup. The prototype focuses on ingestion logic rather than external access setup. |
| Tenant model | One seeded tenant: `Demo Enterprise Client` | The schema is tenant-scoped, but full tenant switching and tenant management UI are out of scope for the prototype. |
| Authentication | No login for the app UI; seeded Django admin users only | The assignment is mainly about ingestion, modeling, review, and decisions. Full auth/RBAC would not improve the core data-trust workflow in a 4-day scope. |
| Emissions engine | Minimal illustrative emission factors | The assignment states that the hard part is messy source data, not building a full carbon factor engine. |
| LLM usage | Groq is optional and analyst-gated | Groq assists with low-confidence text classification only. It cannot invent quantities, dates, kWh, distances, or audit references. |
| Processing model | Synchronous ingestion | Good enough for prototype fixture sizes. Production would use queues/workers for large files. |

These are not accidental gaps. They are scope boundaries I chose so the prototype could go deeper on source-specific ingestion, normalization, validation, provenance, and analyst review.

---

## Tech Stack

**Backend**

- Python 3.11
- Django 5
- Django REST Framework
- PostgreSQL on Render
- SQLite fallback for local development
- `pandas` and `openpyxl` for CSV/XLSX parsing
- `python-dateutil` for mixed date formats
- `groq` SDK for optional LLM suggestions
- `psycopg` for Postgres
- `dj-database-url` for environment-driven database config
- `whitenoise` for static-file serving
- `gunicorn` in production

**Frontend**

- React 18
- Vite
- TypeScript
- React Router
- Tailwind CSS
- Thin fetch client in [`frontend/src/api/client.ts`](frontend/src/api/client.ts)

**Database**

- PostgreSQL in deployment
- SQLite fallback locally
- `JSONField` used for `raw_payload`, `flags`, `field_provenance`, `llm_suggestions`, and `locked_snapshot`

**Deployment**

- Render web service
- Render PostgreSQL add-on
- Single-origin deployment
- Django serves both `/api/*` and the built React SPA from the same host
- No CORS setup required

---

## Architecture at a Glance

The prototype has two connected workflows:

```txt
/ingestion
  → upload or sync source data
  → preserve raw rows
  → apply source-specific rules
  → normalize into activity records
  → assign confidence and validation flags

/review
  → inspect normalized records
  → compare raw vs normalized data
  → review validation issues and provenance
  → accept/reject Groq suggestions
  → approve or lock records for audit
```

The same Django backend powers both workflows. The React SPA provides the analyst-facing interface, while Django REST Framework exposes the APIs for ingestion, review, Groq suggestions, and mock travel sync.

For deployment, the React frontend is built into static assets and served from Django using WhiteNoise. This keeps the deployed prototype single-origin:

```txt
/                         → React SPA
/ingestion                → React route
/review                   → React route
/api/*                    → Django REST API
/api/mock-travel/sync/    → mocked travel source
/admin/                   → Django admin
```

In production, the frontend and backend can be separated later without changing the core data model or API design.

---

## Why This Is More Than CRUD

A simple CRUD app would store uploaded rows and show them in a table.

This prototype does more than that.

For every source row, the system asks:

- Is this row ESG-relevant?
- Is it actual activity or only an accounting/payment/inventory record?
- Is it duplicated, reversed, cancelled, estimated, or incomplete?
- Can the unit, date/period, facility, and activity type be normalized safely?
- Which values came directly from the source?
- Which values came from deterministic rules?
- Which values are missing or AI-suggested?
- Should an analyst approve, reject, request clarification, or lock the record?

That is why the system separates:

- `RawRecord` — what the client originally sent,
- `NormalizedActivity` — the ESG-ready representation,
- `ValidationIssue` — why the row may be risky,
- `field_provenance` — how each value was derived,
- `ReviewLog` — what the analyst did,
- `locked_snapshot` — the frozen audit-ready version.

---

## Duplicate Handling

Duplicates can come from repeated uploads, repeated source rows, amended utility bills, travel resyncs, or the same activity appearing across multiple systems.

The system preserves all raw rows, generates file hashes, row hashes, and source-specific event keys, flags duplicate or double-count risks, reduces confidence, and routes unresolved duplicates to analyst review. This prevents double counting while keeping the original evidence available for audit.

Duplicate rows are never silently deleted. They remain linked to the prior batch, raw row, or normalized activity when a match is found. Analysts can mark a record as duplicate, mark it as not duplicate, use it as the source of truth, or ignore it for reporting with a required comment.

---

## How It Works

### Request Lifecycle: Ingestion

```txt
HTTP POST
  → view
  → source adapter
  → ingestion orchestrator
  → database transaction
```

More specifically:

```txt
Source file / sync trigger
  → parse request
  → source-specific adapter
  → eligibility filtering
  → unit/date/period normalization
  → lookup enrichment
  → validation flags
  → confidence scoring
  → RawRecord + NormalizedActivity + ValidationIssue persistence
  → batch funnel counts update
```

Every source row is preserved as a `RawRecord`, even when the row fails parsing or is intentionally excluded.

---

## Source Adapters

The source-specific ingestion logic lives in:

```txt
backend/ingestion/adapters/
```

| Adapter | Input | What it owns |
|---|---|---|
| [`sap.py`](backend/ingestion/adapters/sap.py) | MB51 / ME2M CSV or XLSX | German/English header detection, EU/US number parsing, movement-type filtering, purchase vs consumption handling, reversal linking, plant/material lookup, unit normalization. |
| [`utility.py`](backend/ingestion/adapters/utility.py) | Utility portal CSV | Charge-type filtering, billing-period validation, calendar-month pro-rata, estimated-reading handling, gas-row rejection, meter-to-facility lookup. |
| [`travel.py`](backend/ingestion/adapters/travel.py) | Concur/Navan-shaped JSON | Segment normalization, cancellation/refund filtering, leg grouping, codeshare deduplication, distance resolution, hotel room-night calculation, cabin-class mapping. |

All adapters return an adapter result containing activity drafts, raw payloads, validation flags, and exclusion reasons. The orchestrator persists them in one transaction.

---

## SAP Handling

The SAP adapter focuses on realistic SAP onboarding exports:

- MB51-like fuel movement export,
- ME2M-like procurement fallback export.

Main SAP rules:

- `261` / `201` → fuel consumption,
- `101` → goods receipt / fuel purchased, not direct emissions,
- `301` / `311` → stock transfer, excluded from emissions,
- `551` → scrapping/write-off, needs review,
- `262` → reversal, linked and netted where possible,
- unknown movement type → needs analyst review.

The adapter also handles:

- German and English headers,
- mixed date formats,
- European and US number formats,
- plant lookup,
- material lookup,
- unit mapping,
- duplicate documents,
- suspicious high quantities,
- spend-based fallback for weak procurement rows.

### SAP Ingestion Design: File Upload Prototype

SAP ingestion is modeled as a controlled file-upload flow because real SAP integrations require client-specific credentials, SAP module permissions, network access, and field mapping.

The prototype accepts MB51/ME2M-style CSV exports through:

```http
POST /api/ingestion/sap/upload/
```

with multipart form data:

```txt
file=<sap export csv>
kind=mb51 | me2m
```

The backend then:

1. reads the uploaded file bytes,
2. calculates `file_hash` and normalized `content_hash`,
3. parses the CSV with delimiter and header detection,
4. applies SAP-specific column aliases, including German headers,
5. runs movement-type and procurement rules,
6. preserves every row as `RawRecord`,
7. creates normalized activities for ESG-relevant rows,
8. flags exclusions, duplicates, reversals, missing lookups, and low-confidence rows.

So the SAP flow is:

```txt
SAP MB51/ME2M export
-> POST /api/ingestion/sap/upload/
-> file hash + row hash + SAP event keys
-> SAP adapter applies movement/procurement logic
-> ingestion batch and review records are created
```

This mirrors the realistic first step of SAP onboarding: the customer shares an export before a live SAP connector exists. A future SAP OData/RFC connector can feed the same adapter and normalized model.

---

## Utility Handling

The utility adapter focuses on electricity usage exports.

Main utility rules:

- `usage_kwh` is preferred over `total_amount`,
- amount-only rows become low-confidence spend-based fallback,
- billing periods are preserved,
- billing periods crossing months are prorated by days,
- `usage_per_day` is calculated for better spike detection,
- estimated readings are flagged and capped in confidence,
- overlapping billing periods are flagged as possible amended bills,
- multiple meters per site are preserved and aggregated at query time,
- tax-only, late-fee-only, deposit-only, payment-only rows are excluded,
- gas rows inside electricity imports are rejected with `GAS_UTILITY_DATA_DETECTED`.

This avoids treating utility bills as simple finance rows and keeps the focus on actual energy consumption quality.

### Utility Ingestion Design: File Upload Prototype

Utility ingestion is modeled as a utility-portal CSV upload. Real utility integrations vary heavily by provider, portal, meter setup, and billing format, so the prototype focuses on the data-quality work after a structured export is available.

The prototype accepts electricity CSV exports through:

```http
POST /api/ingestion/utility/upload/
```

with multipart form data:

```txt
file=<utility electricity csv>
```

The backend then:

1. reads the uploaded file bytes,
2. calculates `file_hash` and normalized `content_hash`,
3. parses the CSV,
4. identifies account, meter, provider, usage, amount, and billing-period fields,
5. applies meter-to-facility lookup,
6. excludes non-consumption rows such as tax, late fees, refunds, and gas rows,
7. prorates billing periods across calendar months,
8. preserves every row as `RawRecord`,
9. creates normalized electricity activities,
10. flags estimated readings, amount-only rows, duplicate bills, overlapping periods, and amended-bill risks.

So the utility flow is:

```txt
Utility portal CSV
-> POST /api/ingestion/utility/upload/
-> file hash + row hash + utility event keys
-> utility adapter applies billing-period and meter logic
-> ingestion batch and review records are created
```

This keeps raw bill evidence intact while preventing fees, estimates, amended bills, and overlapping meter periods from becoming clean audit-ready data without review.

---

## Travel Handling

The travel flow is modeled as a Concur/Navan-like API sync.

Travel categories include:

- flights,
- hotels,
- car rentals,
- rail,
- rideshare/taxi,
- expense-only rows,
- cancelled/refunded/voided bookings.

Main travel rules:

- cancelled/refunded/voided records are stored as raw evidence but excluded from normalized activity,
- expense-only rows without travel evidence are excluded,
- flight legs are grouped using `leg_id`,
- round trips are not double-counted when separate legs already exist,
- flight distance is resolved from source distance or airport lookup,
- the LLM is not allowed to invent flight distance,
- hotel room-nights are calculated from check-in/check-out,
- missing checkout blocks hotel-night calculation,
- room-nights are not multiplied by employee count,
- bundled packages are flagged for review,
- rideshare amount-only rows are low confidence.

---

## Travel Ingestion Design: Pull + Push Prototype

The current travel flow supports both realistic integration styles:

1. **Pull sync**: the analyst selects a date range and Breathe ESG pulls Concur/Navan-shaped trips from the mock provider.
2. **Push upload**: the analyst/data-ops user uploads Concur/Navan-shaped JSON into the mock provider pool, then runs the same sync flow.

This keeps the travel adapter transport-agnostic. It does not care whether records came from a bundled fixture, a mock provider API, a JSON upload, a real Concur/Navan API, or a scheduled background sync.

### Pull sync

From the frontend, the user triggers:

```http
POST /api/ingestion/travel-sync/
```

with a date range:

```json
{
  "start_date": "2025-02-01",
  "end_date": "2025-05-31"
}
```

The backend then:

1. reads all available mock-provider trips,
2. includes both bundled fixture trips and any trips previously uploaded through the push endpoint,
3. filters trips by the requested date range,
4. runs the records through the travel adapter,
5. creates an `IngestionBatch`,
6. stores `RawRecord`, `NormalizedActivity`, and `ValidationIssue` rows.

So the pull flow is:

```txt
Frontend date range
-> POST /api/ingestion/travel-sync/
-> backend reads mock-provider travel pool
-> travel adapter normalizes records
-> ingestion batch is created
```

### Push upload into the mock provider

The prototype also supports uploading travel JSON:

```http
POST /api/mock-travel/upload/
```

It accepts either:

- multipart upload with a `.json` file in Concur/Navan shape, or
- JSON body shaped like `{ "trips": [...] }`.

Uploaded trips are appended to the mock provider pool and become visible to the next:

```http
GET /api/mock-travel/sync/
POST /api/ingestion/travel-sync/
```

The upload endpoint validates basic shape, rejects duplicate `trip_id` values already present in the bundled fixture or upload pool, and returns accepted/rejected counts.

### Endpoint roles

```txt
/api/mock-travel/upload/      -> push new mock travel trips into the provider pool
/api/mock-travel/uploads/     -> inspect or clear uploaded mock trips
/api/mock-travel/sync/        -> preview provider trips by date range
/api/ingestion/travel-sync/   -> create an ingestion batch from provider trips
```

This mirrors two real-world onboarding modes:

- a provider-style pull integration, where Breathe ESG polls Concur/Navan by date range,
- a file/API push workflow, where a customer or data-ops process provides travel JSON first.

Both paths feed the same `travel_adapter.adapt_travel()` logic, so the normalized model, duplicate handling, confidence scoring, and analyst review workflow remain unchanged.

---

## Confidence and Provenance

Every row receives a confidence score from `0–100`.

The score starts from a method ceiling and subtracts fixed amounts for data-quality issues.

Example method ceilings:

| Method | Ceiling |
|---|---:|
| Fuel/activity-based | 100 |
| Distance-based / location-based Scope 2 | 95 |
| Room-night-based | 90 |
| Spend-based fallback | 60 |

Confidence bands:

| Score | Band | Meaning |
|---:|---|---|
| 80–100 | HIGH | Mostly complete; ready for analyst approval. |
| 50–79 | MEDIUM | Usable, but review needed. |
| 30–49 | LOW | Risky; may be eligible for Groq suggestion if enough context exists. |
| <30 | FAILED | Not safely normalizable. |

Every score is reconstructible from flags, which makes it explainable.

`NormalizedActivity.field_provenance` stores how each important value was derived:

```json
{
  "quantity": {
    "method": "DIRECT",
    "source_field": "Menge",
    "confidence": 1.0
  },
  "facility_name": {
    "method": "RULE_BASED",
    "rule": "PlantLookup:1000→Hamburg",
    "confidence": 0.95
  },
  "activity_subtype": {
    "method": "LLM_SUGGESTED",
    "confidence": 0.72,
    "reason": "Material description contains HSD and genset fuel"
  }
}
```

Trust hierarchy:

```txt
DIRECT > RULE_BASED > ANALYST_OVERRIDDEN > LLM_SUGGESTED > MISSING
```

---

## Groq LLM Suggestions

Groq is optional and used only as an assisted reasoning layer.

The Groq service lives in:

```txt
backend/activities/services/groq_suggestion.py
```

It is invoked only for low-confidence rows or when explicitly requested by the analyst.

Groq receives:

- raw source payload,
- partially normalized record,
- missing fields,
- validation flags,
- available lookup context,
- confidence score.

Groq may suggest:

- material category,
- fuel type,
- spend category,
- ESG relevance,
- scope category,
- review explanation,
- analyst follow-up.

Groq must not generate:

- quantities,
- dates,
- document numbers,
- invoice numbers,
- bill numbers,
- ticket numbers,
- kWh,
- flight distance,
- hotel nights,
- audit references.

The response parser drops suggestions for forbidden fields. This guardrail is enforced in code, not only in the prompt.

Suggestions are stored as `LLM_SUGGESTED`. They do not become final values until an analyst accepts them.

If `GROQ_API_KEY` is missing or Groq fails, the row stays in manual review and ingestion continues.

---

## Approve vs Lock

Approval and audit lock are separate actions.

**Approve**

Means the analyst reviewed the row and accepts it.

**Lock**

Means the approved row becomes frozen evidence.

Locked rows cannot be silently changed. Mutations on locked rows return HTTP `409`.

The lock stores a `locked_snapshot` containing:

- approved user and timestamp,
- raw record reference,
- field provenance,
- validation flags,
- emission factor and version,
- `co2e_kg`,
- active validation issues,
- review comments.

This lets the system answer later:

```txt
What was approved?
Who approved it?
What source data was it based on?
Which rules or suggestions created the values?
What factor version was used?
```

---

## API Reference

Base URL:

```txt
/api
```

All responses are JSON.

Tenant is resolved from `DEFAULT_TENANT_SLUG` in this single-tenant prototype.

### Health

| Method | Path | Response |
|---|---|---|
| `GET` | `/healthz/` | `{ "status": "ok" }` |

### Ingestion

| Method | Path | Body / Params | Response |
|---|---|---|---|
| `POST` | `/ingestion/sap/upload/` | multipart: `file`, `kind` = `mb51` or `me2m` | `IngestionBatch` |
| `POST` | `/ingestion/utility/upload/` | multipart: `file` | `IngestionBatch` |
| `POST` | `/ingestion/travel-sync/` | JSON date range | `IngestionBatch` |
| `GET` | `/ingestion/batches/` | — | list of batches |
| `GET` | `/ingestion/batches/<uuid>/` | — | batch detail |
| `GET` | `/ingestion/batches/<uuid>/raw-records/` | — | raw rows |
| `GET` | `/ingestion/batches/<uuid>/exclusions/` | — | exclusion reasons |
| `GET` | `/ingestion/batches/<uuid>/duplicates/` | — | duplicate raw rows and activities |

### Review

| Method | Path | Body / Params | Response |
|---|---|---|---|
| `GET` | `/review/summary/` | — | aggregate review counts |
| `GET` | `/review/activities/` | filters: `source`, `batch`, `status`, `eligibility`, `confidence`, `flag`, `suspicious`, `locked`, `search` | activity list |
| `GET` | `/review/activities/<uuid>/` | — | activity detail |
| `POST` | `/review/activities/<uuid>/approve/` | optional comment | updated activity |
| `POST` | `/review/activities/<uuid>/reject/` | required comment | updated activity |
| `POST` | `/review/activities/<uuid>/mark-not-relevant/` | required comment | updated activity |
| `POST` | `/review/activities/<uuid>/request-clarification/` | required comment | updated activity |
| `POST` | `/review/activities/<uuid>/override/` | field, new value, comment | updated activity |
| `POST` | `/review/activities/<uuid>/lock/` | — | locked activity |
| `POST` | `/review/activities/<uuid>/groq-suggest/` | optional `force` | Groq suggestion result |
| `POST` | `/review/activities/<uuid>/accept-llm-suggestion/` | field | suggestion accepted |
| `POST` | `/review/activities/<uuid>/reject-llm-suggestion/` | field | suggestion rejected |
| `POST` | `/review/activities/<uuid>/mark-duplicate/` | required comment | duplicate reconciliation logged |
| `POST` | `/review/activities/<uuid>/mark-not-duplicate/` | required comment | duplicate risk resolved |
| `POST` | `/review/activities/<uuid>/use-as-source-of-truth/` | required comment | record selected and approved |
| `POST` | `/review/activities/<uuid>/ignore-duplicate/` | required comment | duplicate ignored for reporting |

### Mock Travel

| Method | Path | Body / Params | Response |
|---|---|---|
| `GET` | `/mock-travel/sync/` | query: `start_date`, `end_date` | Concur/Navan-shaped JSON |
| `POST` | `/mock-travel/upload/` | multipart JSON file or JSON body with `trips` | accepted/rejected upload counts |
| `GET` | `/mock-travel/uploads/` | — | uploaded mock trip pool |
| `DELETE` | `/mock-travel/uploads/` | — | clears uploaded mock trips |

---

## Example API Calls

```bash
curl http://localhost:8000/api/healthz/
```

```bash
curl -X POST http://localhost:8000/api/ingestion/sap/upload/ \
  -F "file=@backend/fixtures/sap/sap_mb51_fuel_movements.csv" \
  -F "kind=mb51"
```

```bash
curl "http://localhost:8000/api/review/activities/?source=sap&confidence=MEDIUM"
```

```bash
curl -X POST http://localhost:8000/api/review/activities/<UUID>/approve/ \
  -H "Content-Type: application/json" \
  -d '{"comment":"Verified against source"}'
```

```bash
curl -X POST http://localhost:8000/api/review/activities/<UUID>/lock/
```

---

## Run Locally

### 1. Setup Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

### 2. Setup frontend

```powershell
cd frontend
npm install
cd ..
```

### 3. Migrate and seed

SQLite is used by default locally. Set `DATABASE_URL` to use Postgres.

```powershell
python backend\manage.py migrate
python backend\manage.py seed_tenant
python backend\manage.py load_lookups
```

### 4. Run in development mode

Backend:

```powershell
python backend\manage.py runserver 8000
```

Frontend:

```powershell
cd frontend
npm run dev
```

Vite runs on `:5173` and proxies `/api` to Django on `:8000`.

---

## Single-Origin Local Mode

To test Django serving the built React SPA:

```powershell
cd frontend
npm run build
cd ..
python backend\manage.py collectstatic --noinput
python backend\manage.py runserver 8000
```

Then open:

```txt
http://localhost:8000
```

---

## Smoke Test

Run all adapters against bundled fixtures without DB writes:

```powershell
python backend\manage.py smoke_adapters
```

This prints funnel counts for SAP, utility, and travel fixture data.

---

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Postgres connection string | SQLite at `backend/db.sqlite3` |
| `DJANGO_SECRET_KEY` | Django secret | dev-only fallback |
| `DJANGO_DEBUG` | Enables debug when `1` | `1` locally, `0` on Render |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hosts | `*` locally |
| `DEFAULT_TENANT_SLUG` | Default tenant slug | `demo-enterprise-client` |
| `DEFAULT_TENANT_NAME` | Default tenant name | `Demo Enterprise Client` |
| `GROQ_API_KEY` | Enables Groq suggestions | unset → graceful no-op |
| `GROQ_MODEL` | Groq model id | `llama-3.3-70b-versatile` |
| `GROQ_TIMEOUT_S` | Groq call timeout | `20` |

---

## Seeded Users

These are for Django admin / review-log attribution.

```txt
admin / admin
analyst / analyst
```

The main app UI itself is intentionally unauthenticated.

---

## Click-Through Demo

With servers running:

1. Go to `/ingestion`.
2. Upload SAP fixture:
   - [`backend/fixtures/sap/sap_mb51_fuel_movements.csv`](backend/fixtures/sap/sap_mb51_fuel_movements.csv)
   - kind = `mb51`
3. Upload utility fixture:
   - [`backend/fixtures/utility/utility_electricity_export.csv`](backend/fixtures/utility/utility_electricity_export.csv)
4. Optionally upload Concur/Navan-shaped travel JSON into `/api/mock-travel/upload/`, then run travel sync:
   - start date: `2025-02-01`
   - end date: `2025-05-31`
5. Open `/ingestion/batches` and inspect batch counts.
6. Open `/review`.
7. Filter for low-confidence or suspicious rows.
8. Open a record detail page.
9. Compare original source row vs normalized activity record.
10. Inspect validation issues and field provenance.
11. Trigger Groq suggestion if available.
12. Accept or reject suggestion.
13. Approve the record.
14. Lock the approved record.
15. Confirm the record shows `locked_snapshot`.

---

## Deploy on Render

The repository includes:

```txt
render.yaml
render-build.sh
Procfile
```

The Render deployment provisions:

- one Python web service,
- one Render PostgreSQL database,
- frontend build served by Django through WhiteNoise,
- database migrations,
- tenant seeding,
- lookup loading.

Before first push, make the build script executable:

```bash
git update-index --chmod=+x render-build.sh   # one-time, before first push
```

Then connect the GitHub repo to Render.

Add `GROQ_API_KEY` in the Render dashboard if you want LLM suggestions enabled. The app still works without it.

Production start command:

```bash
cd backend && gunicorn breathe_esg.wsgi --bind 0.0.0.0:$PORT --workers 2 --log-file -
```

---

## Deployment Choice

I deployed the prototype as a single Render web service backed by Render PostgreSQL.

This means Django serves both:

- the REST API under `/api/*`,
- the built React SPA through WhiteNoise.

I chose this because it keeps the review experience simple: one deployed URL, one backend, one database, no CORS setup, and no separate frontend hosting configuration.

This is a prototype deployment choice, not a production architecture requirement.

In production, I would likely split the system into:

- frontend on Vercel/Cloudflare/CDN,
- Django API service,
- background workers for ingestion,
- object storage for uploaded files,
- managed PostgreSQL,
- secure secret management,
- tenant-aware auth and RBAC.

---

## What To Look For During Review

The most important parts of this prototype are not the visuals alone. The main things to inspect are:

1. **Ingestion batches** — each upload/sync creates a batch with counts for raw, normalized, excluded, failed, suspicious, and low-confidence rows.
2. **Raw vs normalized view** — every normalized activity links back to the original source row.
3. **Source-specific rules** — SAP movement types, utility billing periods, and travel booking statuses are handled differently.
4. **Validation issues** — suspicious or incomplete rows are surfaced instead of hidden.
5. **Field provenance** — the analyst can see whether a value was direct, rule-based, missing, overridden, or suggested by Groq.
6. **Groq guardrails** — Groq suggestions are advisory and cannot create audit-critical numeric values.
7. **Approval vs lock** — approval records analyst sign-off; lock freezes the record for audit.

---

## Final Project Positioning

This prototype converts messy client activity data into analyst-ready ESG records.

It ingests SAP, utility, and travel inputs, stores raw evidence, applies source-specific rules, normalizes units and periods, handles duplicate/reversal/cancellation cases, flags suspicious or low-confidence rows, uses Groq only for safe text-based suggestions, and gives analysts a dashboard to approve, reject, or lock records for audit.

The core value is the ingestion-control layer:

```txt
Not every row is ESG activity.
Not every purchase is consumption.
Not every bill amount is energy usage.
Not every booking is travel.
Not every missing value should be guessed.
```

That is why this system focuses on provenance, confidence, validation, and analyst control before audit lock.
