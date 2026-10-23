# DukaLink

Mobile-first inventory and wholesale-ordering platform for Kenyan duka owners.

- **Documentation:** start at [`docs/README.md`](docs/README.md). Decisions are in [`docs/decisions.md`](docs/decisions.md); progress is in [`docs/implementation.md`](docs/implementation.md).
- **Backend:** Django + DRF in [`backend/`](backend/), PostgreSQL 16.

## Run the backend (Docker)

```bash
docker compose up --build        # API on http://localhost:8000, Postgres on :5434
```

## Run the tests

```bash
docker compose up -d db
cd backend
export DJANGO_SECRET_KEY=local-test-key POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5434
python -m pytest -q              # use DB_ENGINE=sqlite for a quick run (race tests skip)
ruff check .
```
