# rori

Python project scaffold with FastAPI.

## Setup

From the project root (`rori/`):

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On macOS/Linux, activate with `source .venv/bin/activate`.

## Configuration

Copy `.env.example` to `.env` and replace every value:

```bash
copy .env.example .env
```

The app loads `.env` from the project root automatically; real environment variables take precedence. Never commit `.env`.

| Variable | Used for |
|---|---|
| `DATABASE_URL` | PostgreSQL connection (required; the app will not start without it). URL-encode special characters in the password. |
| `RORI_API_KEYS` | `X-API-Key` auth for `/data/*` endpoints, as `key:restaurant_id` pairs separated by commas |
| `JWT_SECRET_KEY` | Signing JWTs for `/auth/*` endpoints |
| `SUPABASE_URL`, `SUPABASE_KEY` | Supabase users/restaurants for signup and login |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Local database via `docker compose up -d` |

## Run

From the project root (`rori/`), not from `app/`:

```bash
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/health

## Legacy recommendation containment

Operational recommendations are unavailable. `POST /run-analysis`,
`GET /recommendations`, and both `POST /run-analysis/{restaurant_id}` and
`POST /analysis/run-analysis/{restaurant_id}` return HTTP 503 with
`{"detail":"OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE"}`, regardless of credentials.
Legacy service calls and rule aggregation also deny unconditionally, without a
configuration switch. Authenticated `/data/*` ingestion still persists data but
does not schedule analysis. Offline economic calculations remain available for
isolated tests; they do not authorize recommendations.
Legacy rule helpers, recommendation formatting/logging and simulation entry points
also deny. `app.rules.calculations` provides numerical-only diagnostics from explicit
observations, without database access or operational instructions.

## Automated tests

```bash
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m pytest
```

The suite runs without PostgreSQL, a running API server, or a `.env` file. Each
local test uses a fresh temporary SQLite database and log directory, test-only
API keys/JWT secret, and blocked outbound socket connections. Application routes,
SQLAlchemy ingestion, recommendation containment, password hashing, and JWT validation
run normally. See [testing details](docs/testing.md) for scope, external checks,
and the migration from standalone scripts.
