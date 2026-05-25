# Breathe ESG — prototype

ESG data ingestion + analyst review. Django REST backend, React/TypeScript frontend, optional Groq LLM-assisted suggestions for low-confidence rows.

Single seeded tenant ("Demo Enterprise Client"). No authentication — that's a deliberate scope choice, documented in [TRADEOFFS.md](TRADEOFFS.md).

## Documentation

I have kept the design rationale in separate documents so the project is easy to review beyond just the deployed app. These docs explain how I approached the assignment, how I modeled the data, what decisions I made, what I intentionally left out, and how I handled realistic source-specific edge cases.

| Document | What it explains |
|---|---|
| [APPROACH.md](APPROACH.md) | My end-to-end approach: problem understanding, architecture, ingestion-review flow, Groq usage, tenant design, and deployment approach. |
| [MODEL.md](MODEL.md) | The core data model: tenants, ingestion batches, raw records, normalized activities, validation issues, provenance, confidence scoring, review logs, and audit lock. |
| [DECISIONS.md](DECISIONS.md) | The key design decisions I made and the reasoning behind each one. |
| [TRADEOFFS.md](TRADEOFFS.md) | The things I deliberately did not build, why I left them out, and what I would do in production. |
| [SOURCES.md](SOURCES.md) | The research links and source-shape evidence I used for SAP, utility data, travel systems, Groq, and ESG platform design. |
| [LOOPHOLES_RESEARCH.md](LOOPHOLES_RESEARCH.md) | The real-world ingestion traps I identified, such as purchase vs consumption, estimated readings, cancelled bookings, duplicates, reversals, and LLM numeric hallucination. |
| [PLAN.md](PLAN.md) | The build plan, shipped scope, milestones, and future improvements. |
---

## Run it locally

```powershell
# Once
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
cd frontend; npm install; cd ..

# (Optional) real Postgres
docker compose up -d postgres
copy .env.example .env       # then edit DATABASE_URL

# Migrate + seed
python backend\manage.py migrate
python backend\manage.py seed_tenant     # creates Demo Enterprise Client + analyst/admin users
python backend\manage.py load_lookups    # loads all fixture CSVs
```

### Dev mode (hot reload, two terminals)

```powershell
# terminal 1
python backend\manage.py runserver 8000

# terminal 2 — Vite at :5173, proxies /api → :8000
cd frontend; npm run dev
```

Open http://localhost:5173.

### Single-origin mode (Django serves the built SPA)

```powershell
cd frontend; npm run build; cd ..
python backend\manage.py collectstatic --noinput
python backend\manage.py runserver 8000
```

Open http://localhost:8000.

**Database default** is SQLite (`backend/db.sqlite3`). Set `DATABASE_URL=postgres://…` in `.env` to use Postgres.

**Groq.** Set `GROQ_API_KEY` in `.env` to enable LLM-assisted suggestions on low-confidence rows. Without it, the suggest button returns a graceful "no key" response and the row goes to manual review.

**Seeded users** (Django admin only — the app itself is unauthenticated):
- `admin` / `admin` — superuser
- `analyst` / `analyst` — implicit reviewer on every `ReviewLog` entry

---

## Click-through

With the servers running:

1. **`/ingestion`** → pick a source.
2. **SAP** → upload `backend/fixtures/sap/sap_mb51_fuel_movements.csv` (kind = mb51).
   28 raw rows → 3 excluded (movement types 311, 301, 561) → 25 normalized activities. Demonstrates German headers, EU dates, a 262 reversal, a duplicate document, a suspicious-high quantity (50,000 L), an unknown plant code.
3. **Utility** → upload `backend/fixtures/utility/utility_electricity_export.csv`.
   23 raw rows → 5 excluded (tax-only / late-fee / amount-only / refund / gas-rejected) → 26 activities (calendar-month pro-rata fanout). Two estimated readings, two Hamburg meters at the same site, an overlapping amended-bill case.
4. **Travel** → date range `2025-02-01` → `2025-05-31`.
   21 trips / 28 segments → 5 excluded (1 cancelled, 1 refunded, 1 voided, 2 expense-only) → 23 activities. A codeshare duplicate, a haversine-estimated flight, a missing-distance flight, a hotel with no checkout, a same-day hotel, a bundled package, a same-city car rental.
5. **`/review`** — summary cards across all batches; each card links to a filtered activity view.
6. **`/review/activities`** → filter `Confidence = LOW`, open one, click **Groq suggest**.
7. On any row: **Approve** → **Lock** → confirm the activity detail shows the audit snapshot.

---

## Smoke test (no DB writes)

```powershell
python backend\manage.py smoke_adapters
```

Runs the three adapters against the bundled fixtures and prints the funnel counts. Useful as a regression check while changing adapter logic.

---

## API tour

The backend is API-first.

```bash
# Health
curl http://localhost:8000/api/healthz/

# Mock travel API (same endpoint the Travel ingestion calls internally)
curl "http://localhost:8000/api/mock-travel/sync/?start_date=2025-02-01&end_date=2025-03-31"

# Ingestion
curl -X POST http://localhost:8000/api/ingestion/sap/upload/ \
  -F "file=@backend/fixtures/sap/sap_mb51_fuel_movements.csv" -F "kind=mb51"
curl -X POST http://localhost:8000/api/ingestion/utility/upload/ \
  -F "file=@backend/fixtures/utility/utility_electricity_export.csv"
curl -X POST http://localhost:8000/api/ingestion/travel-sync/ \
  -H "Content-Type: application/json" \
  -d '{"start_date":"2025-02-01","end_date":"2025-05-31"}'

curl http://localhost:8000/api/ingestion/batches/
curl http://localhost:8000/api/ingestion/batches/<UUID>/exclusions/

# Review
curl http://localhost:8000/api/review/summary/
curl "http://localhost:8000/api/review/activities/?source=sap&confidence=MEDIUM"

curl -X POST http://localhost:8000/api/review/activities/<UUID>/approve/ \
  -H "Content-Type: application/json" -d '{"comment":"Verified against source"}'
curl -X POST http://localhost:8000/api/review/activities/<UUID>/lock/

# Groq suggestion (needs GROQ_API_KEY; without it returns ok:false gracefully)
curl -X POST http://localhost:8000/api/review/activities/<UUID>/groq-suggest/
```

---

## Deploy (Render)

The repo is pre-configured for [Render](https://render.com).

1. Push to a GitHub repo connected to Render.
2. Render reads `render.yaml`:
   - Provisions a free-tier Postgres add-on.
   - Creates a free-tier Python web service.
   - Runs `./render-build.sh` (Python deps → npm build → `collectstatic` → `migrate` → `seed_tenant` → `load_lookups`).
   - Starts `gunicorn breathe_esg.wsgi`.
3. Add `GROQ_API_KEY` as a dashboard env var to enable LLM-assisted suggestions; the app runs without it.

Mark the build script executable before pushing:

```bash
git update-index --chmod=+x render-build.sh
```

`Procfile` is provided as a fallback for Heroku-style providers (Railway, Fly.io).

The Django service serves both `/api/*` and the built React SPA from one origin — no CORS configuration needed.
