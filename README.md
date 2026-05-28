# Risk Assessment Dashboard

A site-incident risk-assessment dashboard built around the Vedanta
`OL_INCIDENTS` dataset.

- **Backend:** FastAPI + SQLAlchemy + APScheduler
- **Database:** PostgreSQL (`vedanta_risk`) managed via pgAdmin
- **ML:** scikit-learn, XGBoost, Prophet, SHAP
- **Frontend:** React + Vite + TypeScript + Tailwind + Recharts

## Where the data comes from

In the live workflow you do **not** run any SQL Server tooling. Someone
hands you a CSV export of the corporate `OL_INCIDENTS` table; you drop it
into `data/raw/`, clean it, and load it into Postgres.

The repo also contains a **legacy, optional** standalone exporter at the
project root (`main.py`) that can pull rows directly from SQL Server via
pyodbc. You do not need to run it. It is kept only for the rare case
where someone needs to refresh `data/raw/` themselves.

## Data flow (your real workflow)

```
You drop a CSV here  →  data/raw/OL_INCIDENTS_<timestamp>.csv
                                   │
                                   │  scripts/clean_csv.py
                                   ▼
                        data/raw/OL_INCIDENTS_clean.csv
                                   │
                                   │  scripts/load_csv_to_db.py
                                   ▼
                        PostgreSQL `ol_incidents` (vedanta_risk)
                                   │
                                   │  scripts/run_pipeline.py  (4 ML steps)
                                   ▼
   risk_scores · predictions_cache · risk_drivers · recommendations · backtest_results
                                   │
                                   ▼
                        backend FastAPI  →  React frontend
```

See `FILE_STRUCTURE.md` for the per-file map.
See `docs/ML_PIPELINE_STATE.md` for ML state and verified row counts.

## Prerequisites

- Python 3.11+
- Node.js 18+ (for the frontend)
- PostgreSQL 14+ running locally with a `vedanta_risk` database created
  in pgAdmin

## Quickstart

```bash
# 1. Install Python deps
pip install -r backend/requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env: set DATABASE_URL to your local Postgres connection string

# 3. (One-time per fresh CSV) Clean and load
python scripts/clean_csv.py
python scripts/apply_migrations.py    # creates ML output tables
python scripts/load_csv_to_db.py      # loads ol_incidents

# 4. (One-time per fresh CSV) Run the ML pipeline
python scripts/run_pipeline.py --trigger manual --verbose

# 5. Start the backend
cd backend
uvicorn app.main:app --reload
# → http://localhost:8000  (Swagger UI at /docs)

# 6. Start the frontend (separate terminal)
cd frontend
cp .env.example .env       # one-time
npm install
npm run dev
# → http://localhost:5173
```

## How retraining works

- The backend starts an APScheduler `BackgroundScheduler` on boot.
- Default cron: `0 2 * * *` (daily at 02:00 UTC). Override via
  `RETRAIN_CRON` in `.env`.
- A successful CSV upload to `POST /api/ingest` also queues a pipeline
  run as a background task.
- `GET /health` returns the next scheduled retrain time.
