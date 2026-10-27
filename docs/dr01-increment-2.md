# DR-01 Increment 2 — audit and trusted persistence foundation

## Status and change control

Work continues on `development/dr01-evidence-contracts-v1`, HEAD
`3f66a088f6a82f21aff76a06b6818fe13536a4df`. Increment 1 arrived as untracked
files; it was preserved and independently reviewed. No branch switch, commit,
push, deployment, operational-data import, or production schema migration occurred.
This document describes an isolated persistence foundation, **not production
recommendation authorization**. Application recommendation behavior is unchanged.

## Independent Increment 1 audit

| Severity | Finding and actual source | Resolution / remaining boundary |
| --- | --- | --- |
| Strength | `evidence_contracts/common.py`, `evidence.py`: strict, frozen, versioned contracts; missing/zero/not-applicable differ; exact revisions and deterministic snapshot digests | Retained. Persistence revalidates JSON even for unsafe `model_copy` / `model_construct` objects. A digest establishes integrity only. |
| Strength | `evidence_contracts/decisions.py`: typed decision, operation, tenant, manifest, snapshots, assessments, policy, evaluation time and invalidation conditions; every ALLOW rejected | Retained; SQL also rejects every ALLOW and every positive assessment. There is no trusted operational policy registry. |
| High | Reference-shaped verification assertions do not establish authority, current revisions, or factual accuracy (`VerificationReference`, `EvidenceCheck`) | Durable verification records are issued only by separately provisioned DB principals with purpose-specific capabilities. Snapshots resolve those records and compare exact bindings. Verifier onboarding and factual verification procedures remain operational prerequisites. |
| High | Frozen objects and audit hash chains alone cannot enforce durable immutability (`audit.py`) | Append-only tables, revoked direct write privileges, triggers, transactional audit, authenticated DB principal binding, and RLS added. Schema owners/superusers remain trusted administrators. |
| High | Existing recommendation routes, cache, direct rule calls and background services bypass evidence (`api/routes.py`, `api/analysis.py`, `services/analysis_service.py`, `rules/engine.py`) | Intentionally unchanged. Production use of these paths as authorized operational recommendations remains blocked on a future gateway integration. |
| High | Existing SQLAlchemy operational tables have no tenant FK/RLS or evidence history (`models/models.py`); Supabase identities are separate (`core/auth.py`, `docs/supabase_schema.sql`) | New schema is tenant-isolated without changing existing tables. HTTP/Supabase identity-to-DB-principal provisioning is **not implemented**. A supplied restaurant ID does not grant access. |
| High | No migration runner/version ledger existed for operational models | Explicit additive, checksummed SQL migration using existing SQLAlchemy; never auto-runs at application startup. Unknown/changed schema versions fail. Existing schema is not adopted or rewritten. |
| Medium | Two classes are named `ReliabilityAssessment`: `data_reliability/reliability.py` is a calculation result; `evidence_contracts/decisions.py` is a versioned reference envelope | No second reconciliation algorithm was introduced. Existing result, states, enums and formulas retained. Module-qualified types have different responsibilities; a future server-side adapter must create the envelope from trusted inputs. Naming remains a discoverability risk. |
| Medium | `confidence` could be misread as a universal score | Added a fixed `confidence_axis='state'` to the new envelope. Forecast and decision confidence cannot be substituted. No economic confidence calculation changed. |
| High | EconomicDecision has no first-class immutable evidence identity; `complete_cycle()` accepts an executed boolean and sets VERIFIED whenever executed (`economic_engine/models.py`, `engine.py`) | Documented existing lifecycle gap; no economic behavior changed. Outcome verification is not input authorization. |
| Medium | Policy and dependency versions are syntactically validated, not registered/resolved | Deliberately no permissive defaults. Unknown policies can be recorded in historical denials and snapshots, never grant permission. Freshness thresholds remain undefined and authorization unavailable. |

No critical defect required discarding Increment 1 or prevented a **disconnected,
deny-only** persistence implementation. Wiring these contracts directly into
production as trusted capabilities would be unsafe. The audit preceded persistence
implementation; no production gateway was added.

## Recommendation entry points and bypasses

The complete call-path audit remains in [Increment 1](dr01-increment-1.md).
Confirmed paths:

* `POST /run-analysis` → `run_analysis(1)` → `run_all_rules` → process-global cache.
* `POST /run-analysis/{restaurant_id}` and `/analysis/run-analysis/{restaurant_id}`
  → `run_full_analysis` → rules → priority sorting → JSON log / HTTP response.
* `GET /recommendations` returns the global cache without tenant/evidence binding.
* `POST /data/pos`, `/data/inventory`, `/data/labor`, `/data/sync` authenticate
  ingestion, commit operational data, then schedule `run_full_analysis`.
* Direct `run_analysis`, `run_full_analysis`, `get_latest_recommendations`,
  `run_background_analysis`, `run_all_rules`, and individual rule calls are public
  Python entry points. `get_latest_recommendations` actually recomputes; it catches
  errors and returns None. Background thread errors are printed and swallowed.
* `log_analysis_run` can distribute actionable text independently of an HTTP gate.
* `EconomicEngine.complete_cycle`, `verify_outcome`, `create_learning` remain direct
  calls. No implemented acceptance or physical execution API was found; lifecycle
  enums/flags do not establish an execution authorization boundary.

There is no evidence-backed durable recommendation publication record, tenant-safe
recommendation cache, or enforced acceptance/execution gate. Blocking only
`complete_cycle()` would leave the generation/publication paths above open.

## Files and responsibilities

Increment 2 adds:

* `app/evidence_store/sql/001_evidence.sql`: schema, constraints, RLS, grants boundary,
  append-only triggers, serialized revision/snapshot writes, verification bindings,
  revocation and transactional audit functions.
* `app/evidence_store/migration.py`: explicit PostgreSQL installation/checksum ledger
  and least-privilege runtime grants; requires separately supplied admin engine.
* `app/evidence_store/repository.py`: explicit engine/tenant transactions, owner/bypass
  login rejection, contract revalidation, immutable append/history reads, server-resolved
  snapshot assembly, revision/revocation resolution, deny-only evaluations, audit checks,
  and atomic quarantined-claim staging.
* `app/evidence_store/verification.py`: independent versioned verifier record and
  VERIFIED/REJECTED result; references, method, purpose, scope/limitations and time.
* `app/evidence_store/legacy.py`: pure dry-run extraction and deterministic quarantined
  raw claims; no InventoryRecord construction or operational-table writes.
* `app/evidence_store/__init__.py`: package marker, no startup side effects.
* `tests/postgres/conftest.py`, `test_evidence_store.py`: opt-in real PostgreSQL tests
  with distinct non-owner writer/verifier/other-tenant logins.
* `tests/postgres/provision.py`: optional disposable Docker PostgreSQL fixture creator;
  random synthetic test password, loopback-only port, private config outside Git.
* `tests/evidence_store/test_legacy_and_verification.py`: pure validation/import tests.
* This document; `pytest.ini` registers the isolated PostgreSQL marker.

Additive Increment 1 contract corrections: `common.py` adds `import_integrity`
verification purpose and `precision_uncertain` reason; `audit.py` adds verification
and legacy-claim subjects; `decisions.py` fixes the new envelope's confidence axis to
state. Schema remains 1.0.0 because these contracts have not been committed,
deployed, or persisted outside the disposable development test database.

Pre-existing untracked Increment 1 contracts/tests/report remain included in the
working tree. No existing tests were removed or assertions weakened.

## Database design and enforcement

The dedicated `rori_evidence` schema contains:

| Table | Purpose / constraints |
| --- | --- |
| `schema_versions` | Version and SHA-256 migration checksum; unknown or changed versions rejected |
| `principal_grants` | Admin-provisioned authenticated login → tenant, actor, explicit capabilities; runtime cannot register itself |
| `objects` | Typed versioned payloads for evidence, verification, snapshot, assessment, eligibility and quarantined legacy claims; tenant/kind/UUID/revision composite PK; previous-revision composite FK; deny-only eligibility, blocked-only assessments, unverified-only source evidence |
| `links` | Exact parent/target revision bindings; composite FKs include the same tenant; reverse target index |
| `revocations` | Append-only revocation records, exact target FK, server actor/time/reason |
| `audit_heads` | Private serialized stream head per tenant, mutable only inside trusted functions |
| `audit_events` | Append-only transactionally emitted contract events with sequence, actor, references, DB timestamp, predecessor digest and canonical content digest |

JSONB payloads retain the strict five contracts without introducing another ORM or
reconciliation implementation. Normalized revision links enforce existence and tenant
identity. Payload shape/semantic validation occurs in the Python repository; SQL
additionally enforces critical identity, revision, tenant, schema and deny-only
invariants. Raw SQL access through a provisioned writer is a trusted service boundary,
not a public arbitrary-JSON API. Not every Pydantic field invariant is duplicated in SQL.

Database enforcement:

* ENABLE + FORCE RLS on objects, links, revocations, audit heads/events. Policies
  resolve `session_user` through admin-owned grants. No caller-controlled tenant GUC.
* Runtime SELECT only on approved history tables. No direct INSERT/UPDATE/DELETE/
  TRUNCATE. PUBLIC table/function access revoked. Writes use fixed-search-path
  SECURITY DEFINER functions with capability and tenant checks.
* Writer cannot verify. Verifier capabilities distinguish `verify:import_integrity`,
  `verify:source`, `verify:count`, `verify:coverage`. Issuer must match provisioned actor.
  Successful import integrity cannot certify a physical count; legacy evidence cannot
  receive observation/source/count/coverage verification.
* UPDATE/DELETE/TRUNCATE triggers reject historical mutation, even ordinary owner DML.
  Trusted schema administrators can alter schema/disable triggers: no claim of protection
  against a malicious DBA. Hashes do not replace privileges, backups or external auditing.
* Corrections append the next revision with explicit immediate predecessor. Advisory
  tenant transaction locks plus expected-head checks serialize competing updates.
  Unsupported transaction isolation is rejected; READ COMMITTED is required.
* Snapshot assembly reads stored records and verifications, compares exact contents,
  validates the deterministic contract digest, and stores exact normalized bindings.
  Resolver rejects revoked snapshots, corrected evidence, superseded/revoked verification,
  missing/wrong/null digests, and tenant mismatch. Historical reads remain available.
* Writes and audit events share the caller transaction. Failed batch/constraint/authority
  checks roll back objects, links and audit/head changes. Audit chains revalidate on read.
* Observation/import/assessment/evaluation/verification timestamps cannot be in the future
  relative to the database clock. The database separately records insertion/audit time.
  Missing observation timestamps remain missing; no freshness window is invented.

Concurrency boundary: snapshot resolution holds the tenant lock until transaction
end. Concurrent correction/revocation waits and is visible to subsequent resolutions.
This does **not** make a snapshot returned to a caller permanently valid. There is no
live authorization/execute transaction yet; a future gateway must resolve and authorize
under the same transaction as a durable operation record, then revalidate at later
publication/acceptance/execution boundaries.

No application engine/settings import, `.env` loading, automatic tenant registration,
new API, startup migration, or production database mutation was introduced.

## Legacy migration strategy: claims and quarantine only

Implemented `prepare_legacy` is a pure dry run over an explicitly supplied export of
`inventory`, `sales`, or `labor`. It preserves every supported raw column, original
primary key, tenant, available date/datetime text and values; a typed NULL remains
NULL, an integer zero remains zero, and a binary float retains Python's round-trip
representation with a mandatory precision warning. Naive/date-only source timestamps
remain raw fields, never become certified observation instants. Unsupported raw types
fail explicitly for manual artifact preservation; they are not dropped or coerced.

The deterministic claim UUID/digest covers tenant, original table/key and original
raw fields. Batch ID and import time are metadata and intentionally do not change
claim identity. Reruns preserve the first durable batch lineage without duplicate
objects/audit events. Changed source contents produce a distinct immutable claim;
old contents remain available. This importer supports the one existing operational
source namespace; multi-database/source namespace onboarding requires an explicit
contract extension before importing potentially colliding identifiers.

Every claim is quarantined with unknown observation time, unresolved item/unit,
missing movement coverage, legacy/unverified flags and applicable precision/invalid
quantity flags. Claims are **not** InventoryRecords, snapshots of verified counts,
complete movement histories, economic inputs, or authorization evidence. Source item
names are preserved as raw text; no ingredient conversion or unit mapping is inferred.
An import-integrity verification of legacy evidence remains distinct from source or
physical-observation verification. No legacy claim is automatically promoted.

`stage_claims` writes a caller-selected batch in one repository transaction. Any
invalid or wrong-tenant row rolls back that batch and its audit events. Recovery is
retrying the same unchanged export/chunk; already successful earlier chunks remain
idempotent. Batch orchestration, a durable job/progress ledger, reviewed source export
manifests and live operational-table readers are **not implemented**. The caller must
retain rejected exports and error records outside this store; failures are raised.
No historical production rows were migrated during this work.

Forward baseline support uses a new OPENING_COUNT evidence identity, explicit observed
quantity/time/item/unit, and a separate authorized count verification. It does not
reference or recertify prior quarantined claims. Coverage and source verification,
period selection and policy still need independent establishment before that baseline
could support a future operational authorization.

## Tests and executed commands

Final results are recorded after both dependency configurations execute. The matrix
separates real database behavior from local validation/application regressions:

| Configuration | Existing regressions | Increment 1 contracts | Increment 2 unit | Real PostgreSQL | Failed | Skipped | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Installed dependencies | 239 | 136 | 21 | 27 | 0 | 1 | 0 |
| `tests/constraints/compat.txt` dependencies | 239 | 136 | 21 | 27 | 0 | 1 | 0 |

Each configured PostgreSQL run: **423 passed, 0 failed, 1 skipped, 0 errors**. PostgreSQL 15
ran in disposable loopback-only Docker databases, including one freshly created by
the checked-in fixture helper. The one skip is explicitly disabled live Supabase
authentication; real Supabase authentication remains unverified. Existing deprecation
warnings remain (8 installed / 16 compatible); warnings were not suppressed.

Executed from `/workspace/RORI-integration`:

```bash
# Baseline independently rerun before persistence work:
/workspace/RORI/.venv/bin/python -m pytest -q --junitxml=/workspace/rori-increment2-baseline.xml

# Final installed suite against the original isolated fixture:
RORI_EVIDENCE_TEST_CONFIG=/tmp/rori-evidence-test.json /workspace/RORI/.venv/bin/python -m pytest -q --tb=short --junitxml=/workspace/rori-increment2-installed.xml

# Verify reproducible provisioning against another fresh isolated database:
/workspace/RORI/.venv/bin/python tests/postgres/provision.py /tmp/rori-evidence-review-fixture.json
RORI_EVIDENCE_TEST_CONFIG=/tmp/rori-evidence-review-fixture.json /tmp/rori-compat-venv/bin/python -m pytest -q --tb=short --junitxml=/workspace/rori-increment2-compat.xml
```

For a new environment:

```bash
python -m venv /tmp/rori-evidence-venv
/tmp/rori-evidence-venv/bin/python -m pip install -r requirements-test.txt
# For the older configuration, also pass -c tests/constraints/compat.txt above.
/tmp/rori-evidence-venv/bin/python tests/postgres/provision.py /tmp/unique-rori-evidence-test.json
RORI_EVIDENCE_TEST_CONFIG=/tmp/unique-rori-evidence-test.json /tmp/rori-evidence-venv/bin/python -m pytest -q
```

The fixture helper requires Docker and `postgres:15` (may need an image pull). It
refuses to overwrite a config, creates synthetic credentials with mode 0600 outside
Git, and never reads `.env` or application DATABASE_URL. PostgreSQL tests **skip** if
not explicitly enabled. Explicit bad/incomplete configuration or connection/migration
failure is an error, never a skip/pass. Only an isolated local database named
`rori_evidence_test` is accepted by the test fixture. Normal tests still isolate
application configuration and operational sessions through the existing conftest.

To run just the new persistence checks, append `tests/postgres tests/evidence_store`
to the configured pytest command. To clean up the helper-created fixture without
printing credentials:

```bash
python - <<'PY'
import json, subprocess
from pathlib import Path
path = Path('/tmp/rori-evidence-review-fixture.json')
config = json.loads(path.read_text())
subprocess.run(['docker', 'rm', '-f', config['container']], check=True)
path.unlink()
PY
```

### Failure simulations and coverage boundaries

Implemented/tested: immutable DML/truncation; direct-write denial; authenticated
DB-principal tenant isolation and cross-tenant refs; competing revisions with exactly
one winner; historical revision retention; snapshot identity/reproducibility/content
and digest tampering (including raw null digest); corrected/revoked evidence and
superseded/revoked verifications; independent verifier privileges and issuer spoofing;
legacy import integrity versus physical verification; empty evidence; NULL versus
zero; invalid inventory quantities (existing contracts/DR-01 tests); missing raw
observation timestamps; unresolved item/unit flags; float precision; changed source
claim identities; repeat import idempotency; failed batch rollback/retry; transactional
audit chain consistency; unknown schema versions; future timestamps; denied positive
assessments/ALLOW attempts at SQL boundaries; forward baseline isolation; unsupported
transaction isolation; and concurrent revocation serialized with snapshot resolution.

Unknown policy/manifest versions cannot authorize: all ALLOW remains rejected.
There is **no age-based freshness policy**, trusted assessment adapter, live authorization
operation, or production gateway yet. Tests do not claim to establish freshness
thresholds, concurrent revocation during a real authorization/publication, or protection
of background/legacy recommendation routes. Those are explicitly outstanding gateway
integration tests. Existing economic/reliability regressions verify unchanged behavior;
no formulas, prioritization, confidence calculations or outcome-learning source changed.

## Remaining risks, approvals and smallest next increment

Production blockers:

1. Existing recommendation/cache/background/direct-service paths remain unprotected.
2. Supabase/HTTP identities are not mapped to trusted evidence DB logins. Separate
   provisioning, least-privilege deployment roles and non-owner schema installation
   must be reviewed. Existing operational tables remain outside new RLS protection.
3. Trusted decision IDs, dependency manifests, policy registry, source/coverage rules,
   freshness rules and operation-specific checks are absent; all positive evaluations
   remain blocked. Persistence of a denial is not a gateway evaluation.
4. A server-side adapter must produce blocked/eligible assessment envelopes from the
   existing DR-01 evaluator and trusted exact inputs; do not trust caller-shaped checks.
5. DBA/backup/restore, externally anchored audit monitoring, clocks, verifier onboarding
   and revocation operating procedures need deployment review. A hash chain cannot
   defeat a malicious schema administrator.
6. Real Supabase auth and a Supabase-hosted PostgreSQL deployment have not been tested.
   PostgreSQL 15 in Docker is tested, not every PostgreSQL release or hosted role model.
7. Migration is quarantined staging of explicit exports only; source manifests, source
   namespaces beyond the existing DB, migration job ledger, reviewed item conversions,
   approved baseline periods and production runbooks remain to be implemented.

Later improvements: per-item concurrency instead of conservative tenant serialization;
large snapshot/audit pagination; JSONB growth/retention and external artifact lifecycle;
independent database constraint review; stronger distributed audit anchoring.

Founder/operational decisions required before any rollout: verifier identities and
methods, authoritative source ownership/completeness, tenant identity mapping, source
namespace ownership, operation-specific dependency manifests, freshness/coverage policy
versions, new physical baseline procedure and migration approval. No universal thresholds
or historical verification claims were invented to bypass these decisions.

Smallest next milestone: implement a **deny-only server resolver and DR-01 envelope
adapter**, using this store, with explicit identity and policy registries. Test missing,
unknown, contradictory, stale, revoked, superseded and cross-tenant inputs, including
transactional revision/revocation races. Then integrate generation/publication together
with durable decision identity, tested background/direct-service enforcement and
separate diagnostic calculations. Keep ALLOW disabled until reviewed policies and all
relevant operation boundaries are enforced. Acceptance/execution require later explicit
gates and revalidation, never reuse a global eligibility flag.

## Final repository verification

Both interpreters also executed `python -m pip check`: no broken requirements.
The default installed suite without PostgreSQL configuration was executed separately:
`/workspace/RORI/.venv/bin/python -m pytest -q --tb=short --junitxml=/workspace/rori-increment2-default.xml`.
Result: **396 passed, 0 failed, 28 skipped, 0 errors** (27 explicitly disabled
PostgreSQL checks plus the live Supabase check). These skips do not replace the
27 real PostgreSQL passes in each configured run above.

`git diff --check` and whitespace checks for untracked source passed. The only
tracked-file change is the PostgreSQL marker in `pytest.ini`; economic, rules,
reconciliation, API and authentication source match HEAD. There are 22 untracked
source/test/documentation files, including preserved Increment 1 work. No files
are staged. No environment files, credentials, generated logs or temporary artifacts
are included in the review patch. Temporary test credentials and JUnit outputs
remain outside the repository. No commits or pushes occurred.

Review artifact: `/workspace/rori-dr01-increment2-review.patch` contains both the
preserved uncommitted Increment 1 additions and Increment 2 changes against HEAD.
The disposable PostgreSQL fixtures remain available for review; no production
database schema or operational data was changed.
