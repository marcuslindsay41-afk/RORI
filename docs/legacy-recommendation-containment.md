# Containment boundary remediation — final report

## Verdict and preservation

**APPROVE FOR LOCAL PRESERVATION COMMIT**, subject to founder approval. This is
source preservation readiness, not production authorization or deployment approval.
The blocking lower-helper/persistence boundary is closed in the reviewed source.

Repository `/workspace/RORI-integration`, branch
`development/dr01-evidence-contracts-v1`, baseline and final HEAD
`f917c017b7994ef905a483155b809cd89ff23ead`. Preflight verified the exact existing
16-file uncommitted patch against its SHA-256 inventory, an empty index and no
unexpected changes. That earlier work was preserved; only the authorized remaining
boundary, its tests and documentation changed. The prior phase report is retained
as a historical appendix below and is superseded by this current report.

## Newly protected functions

Every listed function now unconditionally raises
`OperationalRecommendationsUnavailable('OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE')`
before inspecting its arguments, reading/writing data, formatting instructions,
logging, printing, seeding or creating threads. No enabling flag, caller boolean,
identity, test exception or positive authorization fallback exists.

| File | Newly protected functions |
|---|---|
| app/rules/engine.py | check_waste; low_performing_items; labor_efficiency |
| app/rules/engine.py | _worst_impact; _format_public_impact; _combine_messages; _waste_rule_meta; _merge_low_sales_meta; _merge_labor_meta |
| app/core/logger.py | log_analysis_run |
| app/core/flatten.py | flatten_recommendation; _flatten_dict |
| scripts/simulate_restaurants.py | simulate_restaurant; simulate_restaurants; simulate_restaurants_concurrent |
| scripts/simulate_restaurants_mock.py | mock_seed_database; mock_run_full_analysis; simulate_restaurants |

These are **18 newly protected functions**. The private message/priority/meta
helpers were also closed rather than leaving a recombination/formatting route.
Synthetic mock scenarios no longer produce recommendation dictionaries or write
analysis logs. Real simulation wrappers deny before database seeding; their old
seed/DB/thread imports are removed. Existing historical logs are not altered.

The previous five internal guards (run_analysis, run_full_analysis,
get_latest_recommendations, run_background_analysis, run_all_rules) remain blocked.
The four HTTP paths retain their exact 503 / generic detail response. No cache read,
service invocation, database access or background scheduling precedes those denials.
The earlier shared guard, all six API modules, the service stubs and original
45-case containment suite are byte-identical to the remediation starting patch.
API-key authorization, ingestion persistence and absence of recommendation scheduling
remain covered by the original tests. No ingestion permissions were broadened.

## Numerical diagnostics instead of actionable helpers

`app/rules/calculations.py` is a small standard-library-only module with three
numerical interfaces:

* inventory_metrics(stock, sold, cost): supplied integer observations -> numeric
  carrying/excess exposure or None below the original diagnostic thresholds.
* revenue_metrics(revenues): a concrete tuple of supplied revenues -> numerical
  distribution statistics. Bottom-item indices identify input positions, not tenants/items.
* labor_metrics(total_rev, total_labor): supplied numbers -> percentages, dollar
  differences and the existing 30% comparison value, without a staffing instruction.

There are no SQL/model/session imports, restaurant IDs, source handles, file/network
operations, recommendation messages, priorities, suggested actions or eligibility/
authorization fields. These functions cannot obtain restaurant records or publish
results. No operational aggregate wrapper replaces the denied functions.

The valid-input financial arithmetic retains stock/sales ratio 3.0, no-sales stock
boundary 20, carrying/spoilage factor 0.08, excess-loss factor 0.15, existing rounding,
revenue averaging/ranking/clamping, and labor threshold 0.30 with the original
rounded cap/overage/headroom calculations. Suggested order-cut values and imperative
messages were recommendation generation, not necessary numerical diagnostics; they
are not exposed through the new module. No new economic thresholds were invented.

Unknown values (None), negative/nonfinite observations, booleans and strings are
rejected. Empty revenue observations retain unknown average; observed zero remains
zero. Nonfinite derived statistics fail explicitly. Validation does not promote
observations to verified evidence. These are legacy diagnostic arithmetic interfaces,
not approved operational profiles or policies, and their estimates are not measured
or verified losses. Economic Engine v1 and DR-01 equations/calculations are unchanged.

## Reproduction and regression evidence

Before remediation, three direct helper tests failed with "Input inspected before
denial": the old helpers attempted to read their supplied session instead of denying.
After remediation all direct helper, persistence, formatting and CLI cases pass.
No new test failures were suppressed or converted into expected successes.

`tests/test_containment_boundary.py` adds **20 cases**:

* 18 actual direct function calls with poisoned session/payload objects and spies
  for file creation, writes, printing and thread creation. The expected typed denial
  must occur without any input/effect spy being invoked or any logs directory created.
* Two fresh-process tests, each run under both dependency configurations. With no
  DATABASE_URL/API-key/JWT/Supabase configuration, guarded modules import without
  loading SQLAlchemy/models and all internal operations deny. Numerical examples
  still calculate $9 inventory exposure and $20 labor difference without a DB.
* The second process also imports the complete FastAPI app using only an explicit
  synthetic `sqlite://` URL, then verifies all four actual HTTP denials without
  API keys or authentication credentials. No external service is contacted.

The child processes intercept the pre-existing root dotenv loader BEFORE the
first app import, preventing access to the real .env; no production switch was
added. The complete ingestion application still requires DATABASE_URL at import.
This test does not claim the whole app starts with no database configuration;
it proves the internal denial modules have no DB dependency and fresh HTTP startup
needs no operational credentials to deny recommendations.

`tests/test_legacy_metrics.py` adds **25 cases** for original numerical results,
thresholds, ranking, zero versus missing, input/derived nonfinite rejection, and
absence of session/tenant/authorization/action fields. No new test skips exist.
The prior 45 security cases are unchanged. Focused security plus numerical tests:
90 passing cases in each dependency configuration.

`tests/test_analysis.py` changes only expectations invalidated by this authorized
closure: analysis logging now denies instead of writing, SQL-backed helpers deny,
and numerical/threshold assertions call explicit-input diagnostics. Existing $9/$20
results, threshold boundaries and tenant data persistence assertions remain. No
positive helper path is enabled for tests. Existing economic-engine, reconciliation,
DR-01, ingestion and authentication regression tests execute unchanged from stage 1.

## Executed test matrix

All PostgreSQL tests used the existing separate, isolated PostgreSQL 15.19 test
instances. Their loopback URLs and test database names were checked without printing
credentials. No containers were provisioned or infrastructure settings changed.
Only synthetic test data/principals and isolated migration-test databases were used.

```sh
env -u RORI_EVIDENCE_TEST_CONFIG -u RORI_TEST_SUPABASE_ALLOW /workspace/RORI/.venv/bin/python -m pytest tests/test_recommendation_containment.py tests/test_containment_boundary.py tests/test_legacy_metrics.py -q --tb=short --junitxml=/workspace/rori-remediation-focused-installed.xml
env -u RORI_EVIDENCE_TEST_CONFIG -u RORI_TEST_SUPABASE_ALLOW /tmp/rori-3b-hardening-compat/bin/python -m pytest tests/test_recommendation_containment.py tests/test_containment_boundary.py tests/test_legacy_metrics.py -q --tb=short --junitxml=/workspace/rori-remediation-focused-compat.xml
RORI_EVIDENCE_TEST_CONFIG=/tmp/rori-3b-recovery-installed-pg.json RORI_TEST_SUPABASE_ALLOW=0 /workspace/RORI/.venv/bin/python -m pytest -q --tb=short --junitxml=/workspace/rori-remediation-installed.xml
RORI_EVIDENCE_TEST_CONFIG=/tmp/rori-3b-recovery-compat-pg.json RORI_TEST_SUPABASE_ALLOW=0 /tmp/rori-3b-hardening-compat/bin/python -m pytest -q --tb=short --junitxml=/workspace/rori-remediation-compat.xml
env -u RORI_EVIDENCE_TEST_CONFIG -u RORI_TEST_SUPABASE_ALLOW /workspace/RORI/.venv/bin/python -m pytest -q --tb=short --junitxml=/workspace/rori-remediation-disabled.xml
/workspace/RORI/.venv/bin/python -m pip check
/tmp/rori-3b-hardening-compat/bin/python -m pip check
```

| Configuration | Passed | Failed | Skipped | Errors | Warnings |
|---|---:|---:|---:|---:|---:|
| Focused installed | 90 | 0 | 0 | 0 | 9 |
| Focused compatible | 90 | 0 | 0 | 0 | 11 |
| Full installed + PostgreSQL | 658 | 0 | 1 | 0 | 12 |
| Full compatible + PostgreSQL | 658 | 0 | 1 | 0 | 20 |
| Full installed, PostgreSQL disabled | 525 | 0 | 134 | 0 | 12 |

Both dependency checks passed. The enabled-run skip is live Supabase authentication;
disabled mode additionally skips the 133 PostgreSQL cases. No mocked authentication
is described as live verification. Warnings are existing dependency/datetime
warnings, not suppressed failures. JUnit confirms 659 collected cases in full runs.

## Exact final changed-file inventory

Relative to HEAD: **23 files — 17 modified, six new**. This comprises the original
16-file containment patch plus seven newly touched files. Twelve files changed
relative to the remediation starting state (marked R below). Unmarked files retain
their prior containment-patch bytes. No staging occurred.

| File | Git state | R / responsibility |
|---|---|---|
| README.md | Modified | R: document numerical-only interface and broader denial |
| app/api/analysis.py | Modified | Earlier HTTP denial, unchanged by remediation |
| app/api/inventory.py | Modified | Earlier ingestion preservation/no scheduling, unchanged |
| app/api/labor.py | Modified | Same |
| app/api/pos.py | Modified | Same |
| app/api/routes.py | Modified | Earlier default/cache denial, unchanged |
| app/api/sync.py | Modified | Earlier sync/no scheduling, unchanged |
| app/core/flatten.py | Modified | R: close recommendation formatting/flattening |
| app/core/logger.py | Modified | R: close recommendation persistence |
| app/core/recommendation_containment.py | New | Earlier unconditional guard, unchanged |
| app/rules/engine.py | Modified | R: close SQL-backed and private recommendation helpers |
| app/rules/calculations.py | New | R: explicit-input numerical-only diagnostics |
| app/services/analysis_service.py | Modified | Earlier four service denials, unchanged |
| docs/n8n_integration_guide.md | Modified | Earlier integration containment guidance, unchanged |
| docs/testing.md | Modified | R: document helper and cold-start tests |
| docs/legacy-recommendation-containment.md | New | R: current final report plus historical appendix |
| scripts/simulate_restaurants.py | Modified | R: deny before real seeding/threading/printing |
| scripts/simulate_restaurants_mock.py | Modified | R: close synthetic generation/logging path |
| tests/test_analysis.py | Modified | R: denied persistence/helpers; preserved numerical assertions |
| tests/test_api.py | Modified | Earlier API/ingestion assertions, unchanged |
| tests/test_recommendation_containment.py | New | Earlier 45-case security suite, unchanged |
| tests/test_containment_boundary.py | New | R: 18 direct boundaries and two cold-start cases |
| tests/test_legacy_metrics.py | New | R: 25 numerical/interface cases |

## Protected boundaries, limitations and final Git status

All 31 protected-file fingerprints match: DR-01 contracts/store/adapter,
reconciliation, reliability, Economic Engine v1, authentication and Supabase schema.
No coverage assurance, verifier authority, revocation or decision-eligibility rule
changed. Migration checksums remain:

```text
001: bf113273fd0d9d9caf08a32b18b75b8e4e7732febcb663590f46069e823d00ad
002: b01380e368d4b2209f6972eb8ea4687d29a3a586a431331dac7523973af922af
```

Source review found no remaining legacy action-producing recommendation interface
outside containment. The remaining numerical functions produce statistics only.
EconomicDecision/Outcome objects and EconomicEngine perform preserved in-memory
calculation/lifecycle work; they do not grant permission or dispatch interventions.
`log_ingestion` writes existing ingestion metadata, not recommendation payloads.
The standalone seed_data maintenance script remains unchanged, generates no
recommendations, and is no longer called by simulation entry points. It was not run.

This is not a Python/DBA sandbox and cannot prevent arbitrary privileged code from
writing files, accessing raw data or inventing instructions. The patch is not
deployed and does not terminate older processes or work already running elsewhere.
Historical logs and evidence remain untouched. Hosted exposure, live Supabase,
authentication placeholders/errors, role provisioning, and the future authorization
gateway remain unverified or deferred. Repeated PostgreSQL fixture use still retains
ACL entries; fresh fixtures are advisable before extensive future reruns. No cleanup
policy or infrastructure setting was changed to obtain passing tests.

The branch and HEAD remain unchanged; all 23 files are uncommitted and unstaged,
with an empty index. No push, commit, merge, deployment, production data access,
Supabase change, infrastructure change or Increment 3C development occurred.
Full combined diff: `/workspace/rori-boundary-remediation.patch` (outside repository).
Stop for explicit founder approval before preservation.

---

## Historical appendix — earlier 16-file containment stage (superseded)

The following earlier report records the partial implementation reviewed before
this remediation. Its statements about retained SQL helpers and its 16-file/test
counts are historical, not the current boundary or inventory.

# Legacy operational recommendation containment

## Status and starting checkpoint

Implemented locally on `development/dr01-evidence-contracts-v1` in
`/workspace/RORI-integration`, starting from and retaining HEAD
`f917c017b7994ef905a483155b809cd89ff23ead`. Preflight verified the correct branch,
empty index and clean working tree. No existing work was overwritten.

This is unconditional containment, not positive production authorization or a
DR-01 Economic Decision Gateway. No configuration switch, caller boolean, synthetic
identity or diagnostic aggregate entry point can enable the blocked functions.
No commit, push, deployment, infrastructure change or production access occurred.

## Implemented behavior

All four legacy recommendation HTTP paths return HTTP 503 and exactly:

```json
{"detail":"OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE"}
```

* POST `/run-analysis`
* GET `/recommendations`
* POST `/run-analysis/{restaurant_id}`
* POST `/analysis/run-analysis/{restaurant_id}`

The nested and direct tenant-specific aliases share the same denying handler.
Denial happens before service/database calls, cache reads, rule execution, analysis
logging or scheduling. Anonymous callers, either tenant's API key, a signed JWT,
invalid credentials and caller-supplied eligibility/profile query parameters all
receive the same denial. Ordinary FastAPI method/path/schema validation remains;
for example a non-integer path ID can still receive validation HTTP 422. No such
response authorizes or returns recommendations.

`run_analysis`, `run_full_analysis`, `get_latest_recommendations`,
`run_background_analysis` and `run_all_rules` now raise the typed
`OperationalRecommendationsUnavailable` exception with the same code. The service
module no longer imports database, rules, logging or threading dependencies. It
has no empty-result fallback or exception suppression. Direct rule aggregation
does not touch the supplied session. The old cache variable remains for fixture/
module compatibility but no recommendation handler reads or populates it.

POS, inventory, labor and sync ingestion retain their existing schemas, API-key
tenant mapping, inserts/upserts, commit/rollback behavior and ingestion logging.
They no longer accept/schedule a BackgroundTasks analysis operation. Internal
session-construction and database-operation exceptions handled by these endpoints
return generic HTTP 500 / `DATA_INGESTION_UNAVAILABLE`, without driver exception
details. Authentication placeholders and authentication error handling are excluded
and unchanged; this is not a claim that every application error is sanitized.

## Calculation preservation and test changes

Economic Engine v1, reconciliation, reliability, DR-01 contracts, store, adapter,
verification and identity code remain byte-identical. Every individual pre-existing
rule calculation/helper and threshold in `app/rules/engine.py` is AST-identical;
only operational `run_all_rules` aggregation is replaced by denial.

Offline rule tests still exercise actual tenant-filtered synthetic SQL data,
waste calculations (including the existing $9 result), labor calculations
(including the existing $20 result), thresholds, and missing-revenue semantics.
Existing economic-engine, expected-value, confidence, reconciliation and learning
regression tests execute unchanged. Existing logging utility tests remain.

Only legacy-success expectations invalidated by containment were updated:
HTTP analysis/cache success, service aggregation/sorting/logging, automatic ingestion
analysis, and internal database-error text. The numerical/tenant assertions were
retained against the unchanged lower-level calculations. No tests were removed,
new skips introduced, or unrelated assertions weakened.

Lower-level diagnostic calculations are not an authorization API. They still
require trusted code and a database session; arbitrary Python/DB/file access is
not sandboxed by containment. No new callable aggregate or test-enabling flag was
introduced to replace the disabled services.

## Security regression evidence

`tests/test_recommendation_containment.py` adds 45 cases:

* 20 HTTP cases: four paths across anonymous, two API-key tenants, signed JWT and
  invalid credentials, with a conflicting tenant ID and eligibility/profile claims.
* Four HTTP cases with missing configuration and a hostile cache sentinel.
* Five direct service/aggregation cases with database/rule/log/thread dependencies
  instrumented to fail on access.
* Eight valid/rejected ingestion cases asserting no background scheduling; valid
  cases also assert tenant-scoped persisted rows.
* Eight ingestion session/commit failure cases across all four data endpoints,
  asserting generic errors despite synthetic credential/SQL/trace-like exception text.

Side-effect spies must remain uncalled. Poisoned dependencies are not converted
into false passes; every expected denial/body and absence of effects is asserted.
The new HTTP tests reproduced two forbidden side effects before the implementation.

During test development, the added sync failure variants initially lacked their
module lookup entry (two failures). Pytest 8's monkeypatch reflected on the hostile
cache sentinel's `__class__` during fixture setup (24 errors in the compatible
suite). The fixture now permits that setup reflection while denying content access.
Both harness defects were corrected without changing security assertions or
application behavior to accommodate them. Final complete runs pass below.

## Actual verification

Existing, separate disposable PostgreSQL 15.19 fixtures were used. Configurations
were validated as loopback `rori_evidence_test` databases with synthetic credentials.
No new containers, production services, network rules or persistent application
database settings were provisioned or changed. PostgreSQL fixtures append synthetic
test data/principals and create temporary migration-test databases as before.
Live Supabase authentication was explicitly disabled.

```sh
env -u RORI_EVIDENCE_TEST_CONFIG -u RORI_TEST_SUPABASE_ALLOW \
  /workspace/RORI/.venv/bin/python -m pytest tests/test_recommendation_containment.py -q --tb=short

env -u RORI_EVIDENCE_TEST_CONFIG -u RORI_TEST_SUPABASE_ALLOW \
  /tmp/rori-3b-hardening-compat/bin/python -m pytest tests/test_recommendation_containment.py -q --tb=short

RORI_EVIDENCE_TEST_CONFIG=/tmp/rori-3b-recovery-installed-pg.json RORI_TEST_SUPABASE_ALLOW=0 \
  /workspace/RORI/.venv/bin/python -m pytest -q --tb=short \
  --junitxml=/workspace/rori-containment-installed-final.xml

RORI_EVIDENCE_TEST_CONFIG=/tmp/rori-3b-recovery-compat-pg.json RORI_TEST_SUPABASE_ALLOW=0 \
  /tmp/rori-3b-hardening-compat/bin/python -m pytest -q --tb=short \
  --junitxml=/workspace/rori-containment-compat-final.xml

env -u RORI_EVIDENCE_TEST_CONFIG -u RORI_TEST_SUPABASE_ALLOW \
  /workspace/RORI/.venv/bin/python -m pytest -q --tb=short \
  --junitxml=/workspace/rori-containment-disabled-final.xml

/workspace/RORI/.venv/bin/python -m pip check
/tmp/rori-3b-hardening-compat/bin/python -m pip check
```

| Executed configuration | Passed | Failed | Skipped | Errors | Warnings |
|---|---:|---:|---:|---:|---:|
| Focused containment, installed | 45 | 0 | 0 | 0 | 9 |
| Focused containment, compatible | 45 | 0 | 0 | 0 | 11 |
| Full installed + disposable PostgreSQL 15 | 613 | 0 | 1 | 0 | 12 |
| Full compatible + separate disposable PostgreSQL 15 | 613 | 0 | 1 | 0 | 20 |
| Full installed, PostgreSQL disabled | 480 | 0 | 134 | 0 | 12 |

Each PostgreSQL-enabled run includes all 133 existing real PostgreSQL tests. The
single enabled-run skip is live Supabase authentication; disabled mode additionally
skips those 133 database tests. Both dependency checks report no broken requirements.
Warnings are existing dependency/datetime deprecations; four additional JWT creation
cases exercise the unchanged datetime.utcnow path. No warnings were suppressed.

## Exact changed-file inventory

| File | Responsibility |
|---|---|
| app/core/recommendation_containment.py | New constant, typed denial and unconditional guard. |
| app/api/routes.py | Deny default analysis and cached retrieval without reading cache. |
| app/api/analysis.py | Deny both tenant-specific router registrations. |
| app/services/analysis_service.py | Replace all four legacy operational services with immediate denial. |
| app/rules/engine.py | Deny operational aggregation; preserve individual calculations. |
| app/api/pos.py | Preserve ingestion, remove analysis scheduling, generic internal errors. |
| app/api/inventory.py | Same for inventory upserts. |
| app/api/labor.py | Same for labor upserts. |
| app/api/sync.py | Same for combined ingestion. |
| tests/test_recommendation_containment.py | New 45-case security suite. |
| tests/test_api.py | Update explicitly invalidated analysis/error/background expectations. |
| tests/test_analysis.py | Preserve offline numerical/tenant assertions; assert service denial. |
| README.md | Document unavailable recommendation endpoints and ingestion behavior. |
| docs/n8n_integration_guide.md | Correct ingestion-only key scope and disabled analysis guidance. |
| docs/testing.md | Document containment and offline-calculation coverage. |
| docs/legacy-recommendation-containment.md | This implementation and verification report. |

## Unchanged boundaries and remaining risks

Protected-file fingerprints (31 files) match the starting checkpoint. Migration
checksums remain:

```text
001: bf113273fd0d9d9caf08a32b18b75b8e4e7732febcb663590f46069e823d00ad
002: b01380e368d4b2209f6972eb8ea4687d29a3a586a431331dac7523973af922af
```

Coverage assurance, verifier authority, revocation, DecisionEligibility, Supabase
identity/RLS, authentication placeholders and historical evidence are unchanged.
No production recommendation permission exists. No Increment 3C work occurred.

This patch has not been deployed; no statement is made about containment of an
already running older deployment or already-started work. Existing historical
logs/caches are not erased. Privileged operators can still access raw databases,
files and low-level calculations. Authentication placeholders, existing auth error
details, token revocation, real hosted identity/role mapping and internet exposure
remain separate unresolved concerns. The simulation script can still seed its
configured database before its analysis call is denied; it was not executed or
changed here. Operators must not run it against production data.

The existing disposable PostgreSQL fixtures retain role ACL entries after runs;
fresh disposable fixtures remain advisable for repeated verification to avoid the
previously diagnosed ACL growth issue. No fixture cleanup policy changed here.

## Git status and approval boundary

Branch and HEAD remain unchanged. All 16 files above are uncommitted and unstaged;
the index is empty. Only expected caches are ignored. A full diff including new
files is exported outside the repository at `/workspace/rori-legacy-containment.patch`.
No commit, push, PR, merge, deployment, production database access, live Supabase
change or infrastructure configuration change occurred.

Stop for explicit founder approval before committing or pushing.
