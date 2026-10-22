# Automated testing

Run from the repository root on Python 3.12:

```bash
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m pytest
```

No API server or PostgreSQL container is needed. `pytest.ini` discovers `tests/`
and rejects unknown markers. Dependency versions are bounded for pytest/httpx;
application dependencies keep their existing constraints. In the managed cloud
sandbox, TestClient's event loop needs permission to use local sockets; the run
must have sandbox network access even though local tests block outbound connects.

## Isolation and coverage

`conftest.py` intercepts `dotenv.load_dotenv` before the app import (including
with python-dotenv 1.0), and replaces database/API-key/JWT settings
before importing the app. It removes normal Supabase settings. Every test gets a
new temporary SQLite database and working directory; all application session
factories and engine references use that database, including background tasks.
No test uses the configured development/production database or writes repository
logs. Ordinary tests reject socket connections. No HTTP auth dependency overrides
are used: API keys, password hashing, JWT signing and verification are real.

Tests assert persisted values, tenant isolation, upserts, transaction rollback,
sync behavior, actual background analysis/logs, analysis formats and sorting,
economic thresholds, health, legacy analysis routes, missing/bad authentication,
invalid payloads/dates, and database error responses. Assertions and unexpected
exceptions fail pytest; HTTP 500 is expected only in explicit failure tests.

SQLite validates the current portable ORM operations, not PostgreSQL-specific
behavior, infrastructure readiness, or Supabase service availability.

## Migration and root causes

| Original issue | Resolution |
| --- | --- |
| Pytest absent from declared dependencies | Added `requirements-test.txt`, including explicit HTTP client dependency. |
| Eight setup errors | Old script helper arguments (`restaurant_id`, `email`, `password`, `token`) were mistaken for nonexistent pytest fixtures. Replaced script harnesses with collected tests and explicit fixtures/parameters. |
| False passes | Removed print-only checks, caught exceptions, boolean/tuple returns, and success exit codes after failures. New tests assert status, response structure, persisted data, and expected errors. |
| Direct psycopg2 connection failure | Script passed a SQLAlchemy `postgresql+psycopg2` URL to psycopg2. Replaced with ORM connection/round-trip assertions on the isolated engine. |
| SQLAlchemy query failure | Replaced raw `session.execute("SELECT 1")` with SQLAlchemy `text('SELECT 1')`. |
| Mock full-analysis failure | Old call omitted required restaurant ID; simplistic query mock also could not support filtering/aggregates. Tests now pass explicit tenant IDs and use real ORM sessions. |
| API HTTP 422 responses | Confirmed route schemas and required `X-API-Key` header. Supply valid list bodies and test-only headers. Missing API-key headers and invalid bodies still explicitly expect 422; invalid keys expect 401. HTTPBearer rejects missing/wrong schemes with 403 on older FastAPI and 401 on newer versions; both require the exact denial body. Body `restaurant_id` cannot select the tenant. |
| Incorrect analysis ordering | `run_analysis` returns fixed type order; `run_full_analysis` sorts by priority. Each contract is tested separately with deterministic data. |
| Missing Supabase and broken manual login flow | Local tests assert missing config yields failure, and exercise real JWTs independently. Live login uses one pre-provisioned test account instead of a random signup followed by hardcoded `test@example.com`. No fake remote signup/login success. |
| Tests depended on running API/database and persistent seed data | In-process client, temporary database/logs, deterministic rows; removed the six superseded standalone test scripts. |

## Optional live authentication

The `external` test skips when `RORI_TEST_SUPABASE_ALLOW` is not `1`. Once
explicitly enabled, missing/blank settings and invalid tenant IDs fail immediately.
Supply all of these securely for a **dedicated test project**:

- `RORI_TEST_SUPABASE_URL`
- `RORI_TEST_SUPABASE_KEY`
- `RORI_TEST_SUPABASE_EMAIL`
- `RORI_TEST_SUPABASE_PASSWORD`
- `RORI_TEST_SUPABASE_RESTAURANT_ID`

Use an existing verified test user. Never supply production values. The check
only logs in and validates `/auth/me`; it does not create users/restaurants or
modify remote data. Once opted in, service/credential failures fail the test;
there is no fallback to skipping after a failed request. Response bodies and
tokens are omitted from failure messages. Run with secrets already injected:

```bash
.venv/bin/python -m pytest -m external
```

Live signup success remains unverified without a safely provisioned external
fixture/cleanup workflow. This suite does not claim otherwise.

## Existing limitations preserved

Application behavior was not changed. Inspection also found that the analysis
routes do not enforce bearer authentication; logout is client-side only; email
sending/reset-confirmation are placeholders. `authenticate_user` currently wraps
its own HTTP exceptions as HTTP 500, so incorrect remote login credentials may
produce 500 rather than 401. These are application follow-up issues, not fixes
hidden in testing changes. Existing dependency deprecation warnings remain
visible (Pydantic `min_items`, datetime UTC calls, passlib `crypt`, and the
Starlette/httpx transition).

## Dependency compatibility checks

Use a separate virtual environment to run the older supported dependency stack:

```bash
python -m venv /tmp/rori-compat-venv
/tmp/rori-compat-venv/bin/python -m pip install -r requirements-test.txt -c tests/constraints/compat.txt
/tmp/rori-compat-venv/bin/python -m pip check
/tmp/rori-compat-venv/bin/python -m pytest
```

The constraints exercise older FastAPI, Starlette, python-dotenv, pytest, httpx,
Pydantic, SQLAlchemy, bcrypt, and python-jose APIs. They are test-only; production
requirements and decision rules are unchanged. A dependency resolver must select
mutually compatible versions: independently installing an old Pydantic over a
new Supabase can leave a broken environment. Always run `pip check`.

The installed stack is also tested. These two boundaries are compatibility
checks, not proof of every possible dependency combination or future release.
The project still has open-ended application dependency ranges.
