# Breathe ESG — prototype

ESG data ingestion + analyst review. Django REST backend, React/TypeScript frontend, optional Groq LLM-assisted suggestions for low-confidence rows.

Single seeded tenant (`Demo Enterprise Client`). No authentication — deliberate prototype scope, documented in [TRADEOFFS.md](TRADEOFFS.md).

---

## Documentation

| Document | What it explains |
|---|---|
| [APPROACH.md](APPROACH.md) | End-to-end approach: problem framing, architecture, ingestion/review flow, Groq usage, tenant design, deployment. |
| [MODEL.md](MODEL.md) | Tenants, batches, raw records, normalized activities, validation issues, provenance, confidence, review logs, audit lock. |
| [DECISIONS.md](DECISIONS.md) | 14 numbered design decisions with reasoning + open questions for the PM. |
| [TRADEOFFS.md](TRADEOFFS.md) | What I deliberately did not build, why, and what production would change. |
| [SOURCES.md](SOURCES.md) | Per source: real-world format researched, sample-data choices, what would break in real deployment. |
| [REAL_WORLD_DATA_TRAPS.md](REAL_WORLD_DATA_TRAPS.md) | Real-world ingestion traps: purchase vs consumption, estimated readings, cancellations, duplicates, reversals, LLM numeric hallucination. |
| [PLAN.md](PLAN.md) | Build plan, shipped scope, milestones, future improvements. |

---

## Tech stack

**Backend** — Python 3.11, Django 5 + Django REST Framework, `pandas` + `openpyxl` for CSV/XLSX parsing, `python-dateutil` for mixed date formats, `groq` SDK for the optional LLM layer, `psycopg` (Postgres) with SQLite fallback, `dj-database-url` for env-driven DB config, `whitenoise` for static-file serving, `gunicorn` in production.

**Frontend** — React 18 + TypeScript, Vite, React Router v6, Tailwind CSS. No data-fetching library — a thin `fetch` client in [`frontend/src/api/client.ts`](frontend/src/api/client.ts).

**Database** — SQLite locally, Postgres on Render. Models use `JSONField` for `raw_payload`, `flags`, `field_provenance`, and `locked_snapshot`. Cross-DB flag filtering: native `@>` on Postgres, `icontains` fallback on SQLite.

**Deploy** — Render web service + Postgres add-on via [`render.yaml`](render.yaml); `Procfile` fallback for Heroku-style providers (Railway, Fly.io). Single-origin: Django serves `/api/*` and the built SPA from the same host — no CORS config.

---

## How it works

### Request lifecycle (ingestion)

```
HTTP POST  →  view  →  adapter            →  orchestrator        →  DB
(file/JSON)    (parse  (source-specific      (one transaction:       (IngestionBatch
              + dispatch) parsing, eligibility filter,  RawRecord + NormalizedActivity   + RawRecord
                          unit normalization, lookup     + ValidationIssue, then bump   + NormalizedActivity
                          enrichment, confidence score,  batch funnel counts)            + ValidationIssue)
                          flag generation → ActivityDraft)
```

**Three adapters**, one per source — [`backend/ingestion/adapters/`](backend/ingestion/adapters/):

| Adapter | Input | What it owns |
|---|---|---|
| [`sap.py`](backend/ingestion/adapters/sap.py) | MB51 / ME2M CSV or XLSX | German+English header detection, EU/US numeric sniffing, `MovementTypeMapping` filter (261/201→consumption, 101→purchase, 311/301→excluded, 551→review, 262→reversal), reversal linking, plant + material lookup, unit normalization. |
| [`utility.py`](backend/ingestion/adapters/utility.py) | Utility portal CSV | Charge-type filter (drop tax-only, late-fee-only, refund, adjustment), billing-period validation, **calendar-month pro-rata fan-out** (one row per overlapping month, scaled by `days_in_month / total_days`), estimated-reading capping, gas-row rejection, `MeterFacilityLookup` resolution. |
| [`travel.py`](backend/ingestion/adapters/travel.py) | Concur/Navan-shaped JSON | Per-segment normalization (flight/hotel/car/rail/rideshare), cancellation/refund/void filtering, leg grouping by `leg_id`, codeshare dedup, distance resolution (provided → haversine via `AirportLookup` → MISSING; LLM never invents distance), hotel room-nights = `(checkout − checkin) × rooms`, cabin-class defaults. |

All three adapters return an `AdapterBatchResult` (list of `ActivityDraft` + `RawRecord` payloads + exclusion reasons). The orchestrator persists everything in one transaction.

### Confidence + provenance

[`backend/ingestion/services/confidence.py`](backend/ingestion/services/confidence.py) — every row starts at the method's ceiling (`fuel_based`=100, `spend_based`=60, etc.) and subtracts a fixed amount per flag. Final score bands into `HIGH` (80+) / `MEDIUM` (50–79) / `LOW` (30–49, LLM-eligible) / `FAILED` (<30). Every score is reconstructible from `flags` alone.

`NormalizedActivity.field_provenance` is a per-field JSON map:
```json
{ "quantity":     { "method": "DIRECT",        "source_field": "Menge", "confidence": 1.0 },
  "facility_name":{ "method": "RULE_BASED",    "rule": "PlantLookup:1000→Hamburg", "confidence": 0.95 },
  "activity_subtype": { "method": "LLM_SUGGESTED", "confidence": 0.72, "reason": "…" } }
```
Trust hierarchy: `DIRECT > RULE_BASED > ANALYST_OVERRIDDEN > LLM_SUGGESTED > MISSING`.

### Groq (optional)

[`backend/activities/services/groq_suggestion.py`](backend/activities/services/groq_suggestion.py) — invoked only for `LOW`-band rows. JSON-mode call; response parser **drops any suggestion targeting a forbidden field** (`quantity`, `dates`, `document_number`, `distance_km`, `usage_kwh`, `amount`, …) — the numeric-vs-text boundary is enforced in code, not just in the prompt. Suggestions land in `field_provenance` as `LLM_SUGGESTED`; rows with unreviewed suggestions cannot be locked. Per-(raw_record, missing_fields) cache in `GroqSuggestionCache` prevents repeat paid calls. Missing `GROQ_API_KEY` → graceful `{ok: false}`, row stays in manual queue.

### Approve vs lock

Two distinct endpoints, two distinct timestamps. `approve` records analyst sign-off. `lock` freezes `field_provenance + flags + EF + co2e + version` into `locked_snapshot` JSON; mutations on locked rows return HTTP 409. See [MODEL.md](MODEL.md) for the full audit trail design.

---

## API reference

Base URL: `/api`. All responses are JSON. Tenant is resolved from `DEFAULT_TENANT_SLUG` env (single-tenant prototype).

### Health

| Method | Path | Response |
|---|---|---|
| `GET` | `/healthz/` | `{ "status": "ok" }` |

### Ingestion — [`backend/ingestion/urls.py`](backend/ingestion/urls.py)

| Method | Path | Body / Params | Response |
|---|---|---|---|
| `POST` | `/ingestion/sap/upload/` | multipart: `file` (CSV/XLSX), `kind` (`mb51` \| `me2m`) | `IngestionBatch` with funnel counts |
| `POST` | `/ingestion/utility/upload/` | multipart: `file` (CSV) | `IngestionBatch` |
| `POST` | `/ingestion/travel-sync/` | JSON: `{ "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD" }` | `IngestionBatch` (calls the mock travel API internally) |
| `GET` | `/ingestion/batches/` | — | List of batches with status + counts |
| `GET` | `/ingestion/batches/<uuid>/` | — | Single batch + lookup-version snapshot |
| `GET` | `/ingestion/batches/<uuid>/raw-records/` | — | All raw rows for the batch (including failed/excluded) |
| `GET` | `/ingestion/batches/<uuid>/exclusions/` | — | Raw rows grouped by `exclusion_reason` |

### Review — [`backend/activities/urls.py`](backend/activities/urls.py)

| Method | Path | Body / Params | Response |
|---|---|---|---|
| `GET` | `/review/summary/` | — | Aggregate counts: pending/approved/rejected/locked, low-confidence, suspicious |
| `GET` | `/review/activities/` | query: `source`, `batch`, `status`, `eligibility`, `confidence`, `flag`, `suspicious=1`, `locked=1`, `search` | List of `NormalizedActivity` |
| `GET` | `/review/activities/<uuid>/` | — | Detail view: activity + raw record + issues + review log + LLM suggestions |
| `POST` | `/review/activities/<uuid>/approve/` | `{ "comment"?: string }` | Updated activity. **409** if locked; **409** if unreviewed LLM suggestions exist |
| `POST` | `/review/activities/<uuid>/reject/` | `{ "comment": string }` | Updated activity. **409** if locked |
| `POST` | `/review/activities/<uuid>/mark-not-relevant/` | `{ "comment": string }` | Updated activity |
| `POST` | `/review/activities/<uuid>/request-clarification/` | `{ "comment": string }` | Updated activity |
| `POST` | `/review/activities/<uuid>/override/` | `{ "field": string, "new_value": any, "comment": string }` | Updated activity; `field_provenance[field].method` → `ANALYST_OVERRIDDEN` |
| `POST` | `/review/activities/<uuid>/lock/` | — | Activity with `locked_snapshot` populated. **409** unless `review_status == "APPROVED"` and no unreviewed LLM suggestions |
| `POST` | `/review/activities/<uuid>/groq-suggest/` | `{ "force"?: boolean }` | `{ ok, cached, model, suggestions[], notes[] }`. Only LOW/MEDIUM by default; `force=true` to override |
| `POST` | `/review/activities/<uuid>/accept-llm-suggestion/` | `{ "field": string }` | Suggestion applied; provenance flips to `ANALYST_OVERRIDDEN` |
| `POST` | `/review/activities/<uuid>/reject-llm-suggestion/` | `{ "field": string }` | Suggestion removed from `llm_suggestions` |

### Mock travel — [`backend/mock_travel/urls.py`](backend/mock_travel/urls.py)

| Method | Path | Body / Params | Response |
|---|---|---|---|
| `GET` | `/mock-travel/sync/` | query: `start_date`, `end_date` | Concur/Navan-shaped JSON. Same endpoint the travel ingester calls internally; exposed so you can also inspect the raw shape. |

Example:

```bash
curl http://localhost:8000/api/healthz/

curl -X POST http://localhost:8000/api/ingestion/sap/upload/ \
  -F "file=@backend/fixtures/sap/sap_mb51_fuel_movements.csv" -F "kind=mb51"

curl "http://localhost:8000/api/review/activities/?source=sap&confidence=MEDIUM"

curl -X POST http://localhost:8000/api/review/activities/<UUID>/approve/ \
  -H "Content-Type: application/json" -d '{"comment":"Verified against source"}'

curl -X POST http://localhost:8000/api/review/activities/<UUID>/lock/
```

---

## Run locally

```powershell
# Once
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
cd frontend; npm install; cd ..

# Migrate + seed (SQLite by default; set DATABASE_URL for Postgres)
python backend\manage.py migrate
python backend\manage.py seed_tenant     # Demo Enterprise Client + analyst/admin users
python backend\manage.py load_lookups    # all fixture CSVs

# Dev mode: Vite at :5173 proxies /api → :8000
python backend\manage.py runserver 8000
cd frontend; npm run dev
```

Single-origin mode (Django serves the built SPA on `:8000`):

```powershell
cd frontend; npm run build; cd ..
python backend\manage.py collectstatic --noinput
python backend\manage.py runserver 8000
```

**Smoke test (no DB writes):** `python backend\manage.py smoke_adapters` — runs all three adapters against the bundled fixtures and prints funnel counts.

**Environment variables**

| Var | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Postgres connection string | SQLite at `backend/db.sqlite3` |
| `DJANGO_SECRET_KEY` | Django secret | dev-only fallback |
| `DJANGO_DEBUG` | `1` enables debug | `1` locally, `0` on Render |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated | `*` locally |
| `DEFAULT_TENANT_SLUG` / `DEFAULT_TENANT_NAME` | Seeded tenant | `demo-enterprise-client` / `Demo Enterprise Client` |
| `GROQ_API_KEY` | Enables LLM suggestions | unset → graceful no-op |
| `GROQ_MODEL` | Groq model id | `llama-3.3-70b-versatile` |
| `GROQ_TIMEOUT_S` | Groq call timeout | `20` |

**Seeded users** (Django admin only — the app itself is unauthenticated):
- `admin` / `admin` — superuser
- `analyst` / `analyst` — implicit reviewer on every `ReviewLog` entry

---

## Click-through (with servers running)

1. `/ingestion` → SAP → upload [`sap_mb51_fuel_movements.csv`](backend/fixtures/sap/sap_mb51_fuel_movements.csv) (kind = mb51).
2. Utility → upload [`utility_electricity_export.csv`](backend/fixtures/utility/utility_electricity_export.csv).
3. Travel → date range `2025-02-01` → `2025-05-31`.
4. `/review` summary cards link to filtered activity views.
5. `/review/activities` → filter `Confidence = LOW` → open one → **Groq suggest** → accept/reject suggestion.
6. On any row: **Approve** → **Lock** → confirm the activity detail shows the `locked_snapshot`.

---

## Deploy (Render)

Push to a GitHub repo connected to Render. The included [`render.yaml`](render.yaml) provisions a free-tier Postgres + Python web service; [`render-build.sh`](render-build.sh) runs `pip install → npm build → collectstatic → migrate → seed_tenant → load_lookups`. Add `GROQ_API_KEY` as a dashboard env var to enable LLM suggestions (the app runs without it).

```bash
git update-index --chmod=+x render-build.sh   # one-time, before first push
```
