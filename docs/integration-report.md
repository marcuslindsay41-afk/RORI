# Pytest and DR-01 integration report

## Verdict

Testing infrastructure and both DR-01 repairs are verified. The complete combined
suite now passes on both dependency configurations: 239 passed, 0 failed,
1 skipped, 0 errors per run. The sole skip is disabled live Supabase auth.
Economic Engine v1 and valid economic rules are unchanged. Existing deployment,
external-authentication, and broader application limitations below still apply.

## Branches and preservation

Remote branches were fetched with:

```bash
git fetch origin '+refs/heads/*:refs/remotes/origin/*'
```

Verified remote heads:

| Branch | Commit | Ahead of main |
| --- | --- | --- |
| main | `02357f363f440544dcc76a647a71ea179a00a072` | 0 |
| economic-engine-v1 | `c51fb3b03deea9a63b040109b589eaec345880c8` | 4 |
| dr-01-inventory-reconciliation | `a04a70389500e3a8be0b0a9e4e178575c66e67cd` | 7 |

Economic Engine v1 is an ancestor of DR-01. The verified commit sequence is:

1. `84a93dd` — decision and measurement primitives.
2. `4d24509` — verified economic learning loop.
3. `3fad8cc` — Economic Engine unit tests.
4. `c51fb3b` — Economic Engine defensive tests.
5. `d4902f8` — DR-01 inventory reconciliation and unit tests.
6. `4dba95b` — defensive reliability safeguards.
7. `a04a703` — reliability assessment tests.

`/workspace/RORI` remains on `test/standardize-pytest`, based on main, with the
repaired changes uncommitted. A separate worktree at `/workspace/RORI-integration`
is on `integration/dr-01-pytest`, based directly on the fetched DR-01 head.
Testing changes were applied as a patch and non-conflicting new files copied;
the four inherited development test modules were retained. The existing
`tests/__init__.py` was identical to the new empty package marker.

`app/economic_engine/` retains the decision models, engine, measurement,
verification and learning modules. `app/data_reliability/` retains the inventory
models, reconciliation and reliability modules. Only models.py and reliability.py
received the scoped DR-01 validation repairs below; reconciliation formulas are
unchanged. Economic Engine v1 and legacy economic rules still match HEAD.
The integration work is organized into separate testing-infrastructure and
DR-01 repair commits. Main is not merged. The final pre-commit review fetched
the remote branches again and confirmed that the development heads above
remain current; both complete dependency runs still pass.

## Phase 1 repairs

- Intercept `dotenv.load_dotenv` before importing the app. This prevents opening
  the actual repository `.env` on old and new dotenv releases, without reading,
  editing, copying or relying on that file or the newer disable environment flag.
- Continue replacing database/API/JWT settings with synthetic test-only values;
  remove normal Supabase settings. Each test has temporary SQLite storage/logs.
- Accept HTTPBearer's documented old/new denial codes (403/401), while asserting
  the exact denial body. Newer 401 responses must advertise `Bearer`. Both `/me`
  and `/logout` reject missing and wrong-scheme credentials. Invalid bearer JWTs
  still require 401 and successful JWT validation remains covered.
- Disabled live auth skips. Explicit opt-in with missing/blank settings or an
  invalid/nonpositive tenant ID fails before network access. Unit tests cover
  every missing setting and invalid IDs, without printing values.
- An actual opt-in run with all test settings absent exited 1 with one failure
  listing the missing variable names, rather than skipping successfully.
- Added reproducible older-version constraints. With Pydantic 2.10 the resolver
  must use a compatible SDK (Supabase 2.16), rather than forcing that Pydantic
  under Supabase 2.33. Both final environments pass `pip check`.

## Actual verification results

All runs used Python 3.12.14 and the complete pytest discovery configuration.

| Suite | Dependency stack | Passed | Failed | Skipped | Errors |
| --- | --- | ---: | ---: | ---: | ---: |
| Repaired legacy branch | Installed | 58 | 0 | 1 | 0 |
| Repaired legacy branch | Older compatible | 58 | 0 | 1 | 0 |
| Combined existing tests, before added boundaries | Installed | 81 | 0 | 1 | 0 |
| Before DR-01 repairs | Installed | 107 | 2 | 1 | 0 |
| Repaired integration suite | Installed | 239 | 0 | 1 | 0 |
| Before DR-01 repairs | Older compatible | 107 | 2 | 1 | 0 |
| Repaired integration suite | Older compatible | 239 | 0 | 1 | 0 |

The one skip is disabled live Supabase authentication; no remote authentication
success is claimed. Installed runs emitted 8 deprecation warnings; the older
stack emitted 16. These are visible dependency/application warnings, not hidden
exceptions or reported passes after errors.

| Dependency | Installed | Older compatible |
| --- | --- | --- |
| FastAPI | 0.158.1 | 0.115.0 |
| Starlette | 1.9.0 | 0.38.6 |
| python-dotenv | 1.2.4 | 1.0.0 |
| pytest | 9.1.1 | 8.0.0 |
| httpx | 0.28.1 | 0.27.0 |
| Pydantic | 2.14.1 | 2.10.0 |
| SQLAlchemy | 2.1.6 | 2.0.36 |
| bcrypt | 4.3.0 | 4.0.1 |
| python-jose | 3.5.0 | 3.3.0 |
| Supabase | 2.33.0 | 2.16.0 |

These are verified compatibility boundaries, not exhaustive proof of every
combination or future version allowed by open-ended production requirements.

## Added development checks and blockers

The 23 inherited Economic Engine/DR-01 tests remain collected. Added 28 cases
cover fractional Decimal reconciliation, positive/negative movements, validation,
independent evidence flags, confidence thresholds at 0.60/0.80, invalid confidence
values, and unexecuted decisions without verified learning. Twenty-six of these
new cases initially passed; two identified the following pre-existing gaps
(now resolved by the repairs below):

1. **Required quantity accepts None.** `InventoryRecord(receipts=None)` does not
   reject the input. In `app/data_reliability/models.py`, the validator skips
   None for every quantity, although only physical_count is Optional. The record
   can fail later during reconciliation arithmetic. Regression:
   `test_required_movement_cannot_be_none`.
2. **Contradictory evidence can become decision-eligible.** An expected count of
   100, actual count of 90, and supplied variance of zero, labelled RELIABLE,
   becomes HIGH-confidence and decision-eligible when evidence flags are true.
   `assess_reliability` checks supplied variance but does not cross-check it
   against actual minus expected. Regression:
   `test_contradictory_count_and_variance_cannot_be_decision_eligible`.

Both original failing regressions now pass unchanged. Repairs:

- Only physical_count may be None; all required quantities must remain finite
  Decimal values. Omitted required constructor arguments fail. Negative movement
  quantities remain invalid, while signed adjustments remain valid.
- Reliability assessment validates expected/actual/variance quantities, rejects
  negative counts, and independently computes actual minus expected. Eligibility
  requires agreement with the supplied variance and an actual zero variance,
  alongside the existing state, review flag and evidence requirements. Evidence
  is never rewritten or silently corrected.
- Added 130 regression cases in tests/test_dr01_validation.py covering every
  required quantity, omitted/null/nonnumeric/nonfinite inputs, signed adjustments,
  optional counts, inconsistent variance, invalid results, and state transitions.

Changed files in the DR-01 repair commit (in addition to the testing
infrastructure commit): app/data_reliability/models.py, app/data_reliability/reliability.py,
tests/test_development_contracts.py (the two original defect regressions),
tests/test_dr01_validation.py, and this report. No existing assertion was weakened.

Exact verified commands, from /workspace/RORI-integration:

```bash
/workspace/RORI/.venv/bin/python -m pytest -q --tb=short --junitxml=/workspace/rori-dr01-fixed-current.xml
/tmp/rori-compat-venv/bin/python -m pytest -q --tb=short --junitxml=/workspace/rori-dr01-fixed-compat.xml
/workspace/RORI/.venv/bin/python -m pip check
/tmp/rori-compat-venv/bin/python -m pip check
```

Results: 239 passed, 0 failed, 1 skipped, 0 errors on each stack. Installed/older
runs retain 8/16 deprecation warnings respectively. The two confirmed DR-01
integration blockers are resolved; no remaining failing local tests exist.

The inherited defensive test helper previously inspected the implementation
signature and silently discarded unsupported evidence arguments. It now calls
the known interface directly, so signature regressions surface normally.

## Commands

To reproduce the current installed-environment results:

```bash
cd /workspace/RORI
.venv/bin/python -m pytest

cd /workspace/RORI-integration
/workspace/RORI/.venv/bin/python -m pytest
```

For a portable fresh environment in either checkout:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m pip check
.venv/bin/python -m pytest
```

For the older dependency check in either checkout:

```bash
python -m venv /tmp/rori-compat-venv
/tmp/rori-compat-venv/bin/python -m pip install -r requirements-test.txt -c tests/constraints/compat.txt
/tmp/rori-compat-venv/bin/python -m pip check
/tmp/rori-compat-venv/bin/python -m pytest
```

Sandbox execution requires local socket access for TestClient/AnyIO. Ordinary
tests block outbound connects and do not require a running PostgreSQL/API server.

## Remaining coverage and application concerns

- SQLite ORM tests do not validate PostgreSQL-specific behavior or production
  deployment. No configured development/production data was used or modified.
- Live signup/login success needs a dedicated external project/account. The
  opted-in integration test only logs in with an existing verified user.
- Economic Engine and DR-01 are separate library modules; this change does not
  wire reliability assessment into HTTP ingestion or the legacy analysis rules.
  Persistence and API-level integration of the newer modules remain unverified.
- As preserved upstream, an executed economic cycle marks the decision VERIFIED
  even when verification strength is weak. Learning's verified flag does depend
  on strong evidence. The intended lifecycle semantics need separate review;
  the testing change does not redefine them.
- Existing unauthenticated analysis routes, client-side logout, placeholder
  email/reset handlers, and wrapped remote-login errors remain documented in
  testing.md. Passing local tests do not certify those features as complete.
- Open-ended dependency ranges and deprecations need ongoing matrix maintenance.

Review artifacts outside the repositories: `/workspace/rori-phase1-repaired.patch`
and `/workspace/rori-dr01-integration.patch`, including new untracked files.
