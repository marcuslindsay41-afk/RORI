# DR-01 Increment 3B — trusted inventory assessment adapter

## 1. Executive summary and status

Implemented an inventory-specific **deny-only** assessment path from persisted
snapshots through full verification/coverage resolution, the existing DR-01 domain
functions, and transactional envelope/receipt persistence. No production-approved
profile type exists. Every returned/persisted assessment has `decision_eligible=False`;
all existing DecisionEligibility ALLOW and PostgreSQL deny-only restrictions remain.
This is not an economic decision gateway or production authorization readiness.

| Status | Scope |
|---|---|
| Implemented and tested | Profile/manifest/receipt contracts, authenticated DB resolution, exact inputs and scope checks, certified coverage distinctions, unchanged DR-01 functions, exact Decimal execution, coherence, immutable sidecars, idempotency, rollback/audit failure, real PostgreSQL concurrency and isolation |
| Implemented but not externally verified | PostgreSQL 15 schema/functions under a hosted/Supabase role model; real verifier onboarding and artifact storage; deployment tooling |
| Designed only | A future reviewed operational profile/approval workflow and integration into a decision-specific policy/gateway lifecycle |
| Blocked or deferred | Production approval, freshness policies, real source authority, non-native conversion, location-specific evidence, documented not-applicable rules, multi-stream role aggregation, production baseline/import rollout, recommendation enforcement |

Final exact results are in Section 12. Earlier development failures are not counted
as successful runs. No existing tests were removed, weakened or newly skipped.

## 2. Repository preflight and preservation

Workspace: `/workspace/RORI-integration`.
Branch: `development/dr01-evidence-contracts-v1`.
Baseline HEAD and final HEAD: `725c7d51e679a597014df7d48d55566ff6e9fb10`.

Before editing, verified the clean working tree/index, both preservation commits,
all 23 checkpoint SHA-256 fingerprints and intended fetch/push origin
`https://github.com/marcuslindsay41-afk/RORI.git`. Read the Increment 1/2 reports,
current source/SQL/fixtures and supplied 3A assessment. No implementation divergence
from the report was found. The report's audit predated preservation commits; its
older HEAD is historical, not a current checkpoint discrepancy.

No branch switch, reset, rebase, stash, merge, commit, staging or push occurred.
Existing work was not overwritten. The three intentional tracked-file changes are
additive support changes below. DR-01 calculation/economic source, existing tests,
application routes/services, authentication, dependencies, prior reports and SQL 001
are unchanged. PostgreSQL access used only explicit synthetic disposable configurations;
no production credentials, live tenant data or production database was required.

## 3. Full changed-file inventory

| File | Change / responsibility |
|---|---|
| `app/inventory_assessment/__init__.py` | New server-only diagnostic adapter package |
| `app/inventory_assessment/errors.py` | Typed security, integrity, infrastructure, idempotency and precision failures |
| `app/inventory_assessment/contracts.py` | Versioned profile/reference, source coverage statement, claim, immutable manifest, request, computation provenance and coherent receipt |
| `app/inventory_assessment/arithmetic.py` | Versioned exact Decimal context and explicit resource/precision rejection |
| `app/inventory_assessment/storage.py` | Trusted DB context, profile/manifest resolution, verifier resolution, receipt replay/persistence, explicit admin profile provisioning |
| `app/inventory_assessment/adapter.py` | Validates immutable inputs and reuses domain functions; emits blocked envelope plus deterministic provenance |
| `app/evidence_store/sql/002_inventory_assessments.sql` | New additive profile/manifest/run tables, RLS, immutability and trusted resolver/persistence functions |
| `app/evidence_store/migration.py` | Explicit `install_assessments()` and service grants; recognizes valid v1/v2 checksummed ledgers without auto-upgrading startup |
| `app/evidence_store/repository.py` | Marks repository-issued active transactions for the adapter boundary; preserves old methods and constructor compatibility |
| `app/evidence_contracts/audit.py` | Adds inventory_manifest and assessment_run subject enum values for traceable mutation audit |
| `tests/inventory_assessment/test_contracts_and_arithmetic.py` | New unit/contract/numerical tests |
| `tests/postgres/test_inventory_assessment.py` | New synthetic real-PostgreSQL adapter, adversarial, rollback and concurrency tests |
| `docs/dr01-increment-3b.md` | This implementation report |

The base AssessmentEnvelope payload was not extended or rewritten. Adding a sidecar
is narrower than replacing the public assessment contract or changing its historical
validation rules. The two audit subject values are the only public contract vocabulary
addition; updated readers accept all old events. Old readers with a closed subject enum
cannot read new subject types: deploy matching reader code with the explicit v2 upgrade.
No current public recommendation API imports these components.

## 4. Interfaces and boundaries

```python
assess_inventory_snapshot(
    transaction, snapshot_reference, assessment_profile_reference, request_scope,
    evaluation_context=None, idempotency_key=None, *, manifest_id, manifest_digest
) -> TrustedAssessmentReceipt
```

Deviations from the suggested signature are deliberate:

* An immutable manifest reference/digest is required because the old snapshot alone
  cannot express closed source coverage, no-movement assertions or usage basis.
* Return value contains `.assessment` (the unchanged versioned AssessmentEnvelope)
  and `.provenance` (the exact computation/request bindings). This avoids losing
  provenance or altering historical v1 assessment payloads.
* Caller evaluation contexts are rejected. PostgreSQL supplies actor/time; an
  explicitly admin-provisioned synthetic test profile can fix evaluation-as-of.
  There is no caller boolean, clock, confidence, quantity or reconciliation-result
  parameter that can establish trusted evidence.

`EvidenceRepository.transaction()` marks its issued transaction, which the adapter
requires. This marker is API misuse protection, not a cryptographic Python sandbox:
the actual authorization boundary is the authenticated DB principal, tenant grants,
`assess` capability and database functions. An arbitrary connection/restaurant ID or
manually constructed EvidenceTransaction is not accepted as a trusted adapter context.

The adapter resolves the current exact snapshot using `resolve_snapshot`, not only
historical `get`. It rereads exact stored evidence and correction ancestry and compares
stored records with embedded snapshot content. It resolves every snapshot verification
through PostgreSQL currentness/authority checks and full Pydantic revalidation. It
recomputes even idempotent replay results rather than trusting cached assessment labels.

### Outcomes and errors

* **Blocked assessment:** validly representable missing/unapproved profile or manifest,
  missing/unknown dependencies, uncertified emptiness, ambiguity, unresolved period,
  unsupported location/conversion/not-applicable semantics, unverified evidence or legacy
  lineage. No invented quantities; incomplete numerical fields remain None.
* **AssessmentIntegrityError:** invalid/missing persisted contract, wrong exact binding,
  requested scope mismatch, malformed verification, wrong manifest proof, stale/revoked/
  superseded input, incompatible digest or contradictory receipt/replay.
* **AssessmentSecurityError:** wrong tenant, untrusted transaction/evaluation context,
  denied DB capability, unavailable current verifier authority, synthetic profile used
  outside the explicitly named disposable test database.
* **AssessmentUnavailable:** database, missing migration/function, connection or audit
  infrastructure failure. Never return a successful assessment when required storage fails.
* **UnsupportedPrecision:** nonfinite/unsupported precision or a Decimal trap; never
  silently round to obtain a reliable state.
* **IdempotencyConflict:** same tenant/key used for a changed request or actor.
* Invalid public request/profile/quantity shapes also fail strict Pydantic validation.

Adapter work runs inside a savepoint, so a caught error cannot leave half an adapter
assessment/audit/run committed in an otherwise valid caller transaction. Caller outer
rollback still rolls back every adapter write. Security/failed infrastructure attempts
are not fabricated as committed audit events; comprehensive failed-attempt auditing
remains a later gateway concern.

## 5. Existing DR-01 functions reused

The only full inventory equation is still in
`app/data_reliability/reconciliation.py:reconcile_inventory`:

```text
expected = beginning + receipts + transfers_in - theoretical_usage - recorded_waste - transfers_out + adjustments
variance = physical_count - expected
```

The adapter maps validated role totals to a fresh `InventoryRecord`, calls
`reconcile_inventory()`, then calls `assess_reliability()` (aliased domain type
`DomainReliabilityResult`). The durable contract is imported as `AssessmentEnvelope`.
No domain class was renamed and no formula, business threshold, priority, expected
value, existing confidence calculation or outcome-learning rule was edited.

Inputs missing a mandatory movement do not produce a fake InventoryRecord. If only
the closing count is absent and every other dependency is validated, the existing
optional physical_count=None path produces the domain INCOMPLETE result. Other
precondition failures produce an INCOMPLETE envelope with unknown numerical fields.

Complete zero variance remains RELIABLE; nonzero variance remains REVIEW_REQUIRED;
negative expected inventory remains UNRELIABLE with the existing None variance.
Receipt coherence independently checks numeric/state consistency, not a second
reconciliation equation. A blocked RELIABLE envelope cannot contain expected=1,
actual=5 and variance=0. The generic historical v1 envelope model is unchanged and
is not elevated to trusted output merely by being readable from storage.

Source/count booleans passed to the domain evaluator are derived only after complete
server resolution and verification. `evidence_current=False` remains mandatory because
no approved freshness policy exists. Consequently valid synthetic reliable evidence
has the existing MEDIUM evidence confidence, not fabricated HIGH confidence. Numerical
reliability is separate from operational permission: all assessments remain blocked,
verification_required=True with explicit POLICY_UNAVAILABLE and repair actions.

## 6. Profile, source coverage and verification semantics

The profile is an immutable admin-provisioned inventory assessment configuration,
not one of the seven future decision-specific policies. It binds ID/version/digest,
algorithm, arithmetic, explicit dependency roles/cardinality, UTC interval/count
semantics, native canonical unit/usage basis, source and verifier allowlists and
trusted evaluation-as-of behavior.

Only `DRAFT` and `SYNTHETIC_TEST_APPROVED` status types exist. DRAFT/missing profiles
block calculation. Synthetic profiles are accepted only in `rori_evidence_test`,
with a fixed admin-provisioned evaluation time. This name guard is defense-in-depth,
not proof that a database is non-production; an operator must explicitly provision
an isolated database. Neither profile status can authorize production recommendations.
No production source authority, age limit or approved threshold is registered here.

Declared synthetic semantics:

* Scope is exact restaurant/item/unit/period; UTC timestamps are mandatory. Opening
  count is exactly at period_start, closing count exactly at period_end; movements
  are in `[period_start, period_end)`. No tolerance window is invented.
* One source stream per dependency role; exactly one opening and closing count.
  These are the supported profile semantics, not an assumed policy for old archives.
* Only restaurant-aggregate evidence and native canonical units are supported. Location
  claims, conversion claims and NOT_APPLICABLE mappings are blocked pending reviewed
  contracts; no conversion factor or implicit neutral value is invented.
* Theoretical usage must be explicitly attested as excluding separately recorded waste.
  Unknown or waste-inclusive basis blocks calculation instead of subtracting waste twice.

A CoverageStatement identifies the role, stream ID, source system, exact scope/period,
representation, exact event revisions and unit/usage basis. A CoverageClaim references
an exact persisted COVERAGE verification. That verification and the source observation
it covers bind `coverage:<canonical-statement-digest>` as a supporting artifact. The
coverage observation also needs separate SOURCE verification. Full verified records,
not their identifiers alone, must be in the exact snapshot. Artifact content hashes
are identifiers here; external artifact availability/factual correctness is not proven.

The adapter distinguishes:

| Input | Treatment |
|---|---|
| Observed Decimal zero | Valid observed numerical input when scope/source/coverage checks pass |
| Unknown quantity | INCOMPLETE; never replaced by zero |
| Missing source role/stream | INCOMPLETE; never replaced by zero |
| Empty events/aggregate collection | INCOMPLETE; not proof of no movement |
| Explicit signed verified-no-movements statement, with separate source/coverage proof | Traceable derived numerical zero for that movement role; original claim representation remains in manifest/provenance |
| NOT_APPLICABLE role | Blocked; no approved mapping rule implemented |

Repeated evidence refs, the same source system/event ID under different UUIDs or
external revisions, overlapping aggregates/events, multiple coverage claims per role,
competing counts and unassigned quantitative snapshot records block calculation.
No count is selected based on whether it makes variance zero. Source-event IDs must
be globally unique within a configured source system for this minimal profile;
real source namespace normalization remains a reviewed onboarding requirement.

Current resolver verifies tenant, exact evidence/revision, purpose, VERIFIED status,
full record shape, current verifier grant, profile issuer/method allowlists,
supporting refs, exact scope description, time ordering, revocation and supersession.
Source verification never substitutes for physical COUNT verification, and IMPORT_INTEGRITY
never substitutes for SOURCE/COUNT/COVERAGE. Verification cannot predate the observation
it claims to certify or occur after trusted evaluation-as-of/server time.

Legacy evidence and any correction ancestry containing a legacy claim remain blocked;
changing a legacy revision's kind to OPENING_COUNT cannot promote old data into a new
verified physical baseline. A genuine new baseline needs a new observation identity,
explicit scope/time and separate verification; no historical certification is inferred.

## 7. Decimal determinism

`exact-decimal-1.0.0` computes sufficient working precision from input coefficient
length, aligned exponents and carry headroom. It uses a fresh Decimal Context,
independent of ambient precision, rounding mode, traps and flags, with traps for
inexact/rounded/invalid/overflow/underflow/clamped/float operations. Decimal exceptions
become explicit UnsupportedPrecision failures. The original equation executes inside
this context without changing its operators or rounding its result.

4096-digit working precision and absolute input exponent/adjusted-exponent bounds of
4096 are explicit implementation resource limits, **not economic thresholds**. Carry
and alignment requirements also count against the working precision bound. Inputs
that cannot be evaluated exactly inside those limits are rejected; finite input alone
does not guarantee supported precision. Test contexts at precisions 1, 3, 28, 80 and
100 preserve outputs/digests and restore the caller's context.

## 8. Envelope coherence and computation provenance

The versioned TrustedAssessmentReceipt binds the unchanged envelope to:

* Tenant and exact request scope.
* Snapshot digest and exact evidence/verification revision sets.
* Manifest ID/digest, profile version/digest and availability.
* Algorithm and arithmetic versions and trusted evaluation-as-of.
* Stable sorted structured block details/reasons/actions.
* A digest of calculation output excluding random assessment ID, actor and attempt time,
  and a computation digest over the versioned provenance including fixed evaluation-as-of.

The receipt checks blocked authorization, scope/snapshot/profile bindings, complete
state quantities, independently consistent variance, nonnegative physical counts,
negative expected inventory classification, incomplete quantity semantics and that
check references are among resolved supporting evidence. Persistence/read validation
rechecks these contracts; the adapter additionally rebuilds the result from current
stored facts on replay. The receipt/digest alone is not a caller-held capability.

State confidence remains explicitly separate from forecast confidence and decision
confidence. No universal score or new economic confidence formula was introduced.

## 9. Additive persistence, migration and compatibility

SQL 001 is byte-identical to the checkpoint, SHA-256:
`bf113273fd0d9d9caf08a32b18b75b8e4e7732febcb663590f46069e823d00ad`.
No old object, constraint, trigger, history payload or deny-only guard was rewritten.
Separate tables are needed because profiles are admin-provisioned, manifests are
writer-submitted claims and runs are assessment-service results with scoped uniqueness.
Reusing the old objects kind check would require modifying its existing constraint;
the additive tables avoid that and reuse the existing framework and RLS functions.

New SQL 002 creates:

* `inventory_profiles`: tenant/ID/version PK, immutable profile JSON/digest and DB
  provisioning actor/time; runtime cannot insert or self-approve a profile.
* `inventory_manifests`: tenant/UUID PK, immutable signed coverage-claim manifest/digest.
* `assessment_runs`: tenant/idempotency-key PK, request digest, unique assessment identity,
  exact composite FK to the old assessment object, and immutable versioned receipt.

All new tables have ENABLE + FORCE RLS using existing authenticated-login tenant
mapping, append-only UPDATE/DELETE/TRUNCATE triggers and revoked PUBLIC access.
Runtime SELECT/write-function grants are explicit through `grant_assessment_runtime`.
Fixed-search-path SECURITY DEFINER functions require the existing tenant/capability
checks and locks. Generic SQL functions remain a trusted service/DBA boundary, not
an HTTP API. Complete semantic validation remains mandatory in the Python resolver;
SQL additionally rejects essential malformed verification payloads at the trusted read
boundary. Privileged administrators can still alter schema/triggers; no hash claims
to defeat a malicious DBA.

`install()` remains an explicit v1 initializer, now accepting either the correct v1
ledger or correct contiguous v1+v2 ledger. `install_assessments(engine)` is the only
explicit upgrade entry point. It verifies checksums, serializes migration installation
with the existing migration lock and records version 2 transactionally. It does not
run at application startup. Changed/unknown checksums fail instead of being adopted.

Migration testing used disposable databases only. The initial development fixture
retains its earlier trial v2 checksum; after the final grant-lock hardening a new
fixture was provisioned instead of rewriting its ledger or deleting history. Final
commands use `/tmp/rori-3b-final-pg.json`. An old trial fixture with a different v2
checksum must fail installation; do not repair it by silently changing checksums.
No production schema migration, operational-table import or deployment occurred.

## 10. Idempotency, concurrency and recovery

Idempotency is tenant-scoped and binds the exact request (snapshot, manifest,
profile/digests, scope, availability state) and authenticated actor. The unique
`assessment_runs` key prevents conflicting rows. Same key/same request returns the
same assessment identity; changed request or actor conflicts. A new attempt key can
create a new audit/assessment identity with the same deterministic computation digest
when immutable inputs and trusted evaluation-as-of are identical.

A retry still resolves current snapshots, full verifications and authority, validates
inputs and recomputes the domain result. It compares the coherent recomputation to
the historical receipt; it does not treat a saved label/receipt digest as sufficient
proof. Corrections, revocations, superseded verification or changed authority fail
before a historical receipt can be returned as current. History remains readable.

The existing tenant advisory transaction lock serializes cooperating evidence writes,
manifest writes, assessment evaluation and idempotency insertion. Current principal
and verifier-grant rows are held FOR SHARE through persistence, preventing concurrent
normal authority UPDATE/DELETE from crossing the resolution/write boundary. New
profiles/manifests/runs are immutable. When absent material becomes available, a retry
with an old key conflicts rather than silently changing an earlier blocked result.

Race tests observe PostgreSQL `pg_stat_activity` advisory/row-lock waits, not just
short sleeps. They cover correction/revocation after an assessment has resolved but
before its enclosing transaction commits, and authority removal blocked until the
assessment ends. Subsequent assessment/replay rejects the now-invalid inputs.
Concurrent identical requests return one durable result; concurrent changed requests
have one success and one explicit conflict.

Envelope, assessment mutation audit, receipt and run audit persist in the same
transaction/savepoint. Outer rollback removes all adapter writes. A trigger-injected
failure specifically during run audit rolls back earlier envelope/audit/run changes,
even when the caller catches the typed error and continues the outer transaction.
A real terminated backend produces typed unavailability and recovery on a new
connection. No success or durable audit is fabricated after failure.

This does **not** grant future operation permission. Publication, acceptance, execution,
cache reads, external side effects and freshness/expiry still require a future gateway
and revalidation. The adapter does not hold locks across remote I/O. Administrative
workflows should follow tenant-lock-before-principal-row lock ordering; deadlocks or
service failure fail closed and need an explicit retry, never partial success.

## 11. Security and tenant isolation

Tests use distinct non-owner writer, verifier and other-tenant database logins. Database
principals, not request booleans, establish available tenant/capability access. Profile
provisioning requires schema-admin table privileges; service callers cannot self-approve.
Full verification is independently resolved from durable records and current grants.
All new tables use the same authenticated-login RLS model, exact-tenant assessment FK
and append-only controls as the foundation. Cross-tenant requests fail before unsafe
reads/writes; other-tenant SELECTs return no matching rows. Invalid idempotent payloads
and malformed authorized-SQL data are not treated as trusted adapter results.

Python's repository-origin marker is not an isolation sandbox against malicious
in-process code. Schema owners/superusers and provisioned raw-SQL service roles remain
trusted actors. Complete Python semantic revalidation is essential; SQL shape checks
are defense-in-depth rather than a duplicate Pydantic/reconciliation engine. No generic
append/resolver function was exposed to HTTP clients.

The existing API-key/custom-JWT/Supabase identity bridge is still absent. Existing
operational tables remain outside the new RLS boundary. Importing an app package can
still load the root development `.env` through existing `app/__init__.py`; pytest
intercepts it before imports and all database provisioning here uses explicit synthetic
fixture configuration. No live Supabase credential, production DB or tenant row was used.

## 12. Actual verification commands and results

All commands run from `/workspace/RORI-integration`. The final disposable PostgreSQL
15 fixture was created with the existing helper, using loopback-only port binding,
random synthetic credentials in a private `/tmp` config and a tmpfs data volume:

```bash
env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock info --format '{{.ServerVersion}}'
env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH DOCKER_HOST=unix:///var/run/docker.sock /workspace/RORI/.venv/bin/python tests/postgres/provision.py /tmp/rori-3b-final-pg.json
```

Configured suites must run **sequentially against this single fixture**, or use
separate disposable databases if run in parallel. The existing admin GRANT fixture
can produce PostgreSQL catalog `tuple concurrently updated` errors when two independent
suite processes change schema ACLs concurrently. No fixture exception is suppressed.
Final sequential commands:

```bash
RORI_EVIDENCE_TEST_CONFIG=/tmp/rori-3b-final-pg.json /workspace/RORI/.venv/bin/python -m pytest -q --tb=short --junitxml=/workspace/rori-3b-installed.xml
RORI_EVIDENCE_TEST_CONFIG=/tmp/rori-3b-final-pg.json /tmp/rori-increment3a-compat/bin/python -m pytest -q --tb=short --junitxml=/workspace/rori-3b-compat.xml
/workspace/RORI/.venv/bin/python -m pytest -q --tb=short --junitxml=/workspace/rori-3b-disabled.xml
/workspace/RORI/.venv/bin/python -m pip check
/tmp/rori-increment3a-compat/bin/python -m pip check
```

| Configuration | Passed | Failed | Skipped | Errors | Warnings |
|---|---:|---:|---:|---:|---:|
| Installed + real disposable PostgreSQL 15 | 513 | 0 | 1 | 0 | 8 |
| Older constrained + real disposable PostgreSQL 15 | 513 | 0 | 1 | 0 | 16 |
| Installed, PostgreSQL explicitly disabled | 424 | 0 | 90 | 0 | 8 |

Each configured run contains all 423 previous passes plus **90 new tests**:
28 new unit/contract/numerical tests and 62 new real PostgreSQL adapter cases.
Total real PostgreSQL passes are **89** (27 previous + 62 new). The disabled run
skips those 89 PostgreSQL tests plus the live Supabase check. No new database
behavior is inferred from the disabled run.

The single configured skip is explicitly disabled live Supabase authentication,
which remains unverified. Disabled PostgreSQL skips are reported separately; they do
not replace the actual PostgreSQL passes. Existing deprecation warnings are unsuppressed.
Both dependency checks report no broken requirements; pip's unwritable cache fallback
warning has no effect on dependency consistency.

Development failures were handled rather than hidden: two fixture defects were fixed
(distinct requests reusing a key, and normal assembly correctly rejecting malformed
verification before an intended adversarial path); an invalid Decimal base-exception
trap caused 53 failures in an intermediate run and was corrected; parallel suite trials
against one schema had seven GRANT setup errors per process and were rerun sequentially.
These were not counted as successful results. No failing existing assertion was weakened
and no test was deleted to obtain the final counts.

Coverage includes exact/nonzero/negative results; missing all eight role types; unknown,
observed zero, empty and verified-no-movement distinctions; duplicate/competing counts,
events and coverage; aggregate/event overlap; unassigned quantitative observations;
legacy claims and corrected legacy ancestry; scope/time mismatches; conversion/usage/
not-applicable blocking; missing/unrelated/wrong-revision verification; malformed SQL
payloads; unapproved/missing/digest-mismatched profiles/manifests; verifier revocation and
authority changes; different ambient and default Decimal contexts; high precision and
explicit rejection; replay/conflicting retries; real PostgreSQL mutation/authority races,
idempotency concurrency, isolation/immutability, audit failure, disconnect and recovery.

## 13. Increment 3A findings and disposition

| 3A finding | 3B disposition |
|---|---|
| Snapshot permits unknown record periods and observations outside their declared periods | Diagnostic snapshots remain valid archives; adapter blocks incomplete period/scope and enforces profile-declared movement/count boundaries before calculation |
| A PASSED check can reference nonexistent/unrelated verification | Trusted adapter resolves full records, purpose/authority/scope/proof and exact snapshot binding; no passed check emitted on incomplete preconditions; coherent receipts/replay validated |
| Blocked RELIABLE/HIGH envelope can carry contradictory quantities | Historical base model remains compatible; trusted receipt and adapter enforce state/quantity coherence, and replay recomputes facts |
| Direct authorized SQL can persist incomplete verification JSON | Generic v1 writes remain unchanged; new trusted SQL read boundary checks essential shape and Python revalidates the full record; malformed input is a typed failure |
| Ambient Decimal context changes reconciliation | Controlled, versioned exact context; unsupported precision/traps raise explicit errors; original formula source unchanged |
| Unknown source completeness and usage basis | Immutable structured coverage statements with independently resolved verification, source identity deduplication and explicit waste-exclusive basis; unsupported semantics block |
| No trusted assessment producer or durable replay binding | Server-owned adapter plus immutable receipt/run sidecar and unique scoped idempotency key implemented |
| No approved policies/identity bridge/recommendation gateway | Intentionally still blocked/deferred; no 3C/3D/3E or production authorization implemented |

## 14. Remaining production blockers

1. No production-approved assessment profile, source/verifier onboarding, artifact
   verification operations, source completeness ownership, unit/location/recipe mapping
   or freshness policy. Only synthetic test approvals demonstrate the calculation path.
2. No production HTTP/Supabase identity provisioning into evidence DB principals.
3. No decision-specific dependency/freshness policies, immutable recommendation lifecycle,
   operation gateway, tenant-safe recommendation cache, publication/outbox/acceptance/
   execution enforcement. Existing recommendation/background paths are unchanged.
4. Existing DecisionEligibility requires its policy to equal assessment-reference policy.
   Here the envelope's existing `policy` slot identifies the diagnostic assessment profile.
   Future decision-policy contracts must distinguish assessment configuration from an
   operational decision policy; do not reinterpret this profile as production approval.
5. Hosted PostgreSQL role/RLS behavior, live Supabase authentication, production migration
   deployment/rollback planning, audit retention/anchoring, backups and real operating
   procedures remain unverified. A trusted DBA can still alter the schema.
6. No production legacy import orchestration or historical verification promotion. No
   fabricated historical movements/counts/timestamps or universal freshness thresholds.

## 15. Known limitations and unresolved founder decisions

The minimal profile deliberately supports native canonical units, restaurant-aggregate
scope, exact UTC boundaries and one source stream per role. It does not claim those are
approved real-world operating semantics. Missing conversion lineage, multiple streams,
location specificity, not-applicable mappings or a real business calendar need explicit
reviewed contract/profile evolution; they cannot be filled in by defaults.

Coverage/verification references commit to supporting artifact identities, but this
increment does not fetch external artifacts or prove factual accuracy. Separate source
and physical-observation verification records are required, but real organizational
independence/method standards must be approved. Source event namespace uniqueness and
profile approval governance need onboarding decisions. Database naming is not a substitute
for deployment isolation, and direct SQL access must remain restricted to trusted services.

Administrative profile provisioning retains immutable DB role/time and approval
references, but is not integrated into the runtime event hash chain. Production
approval governance and its audit workflow remain a 3C design requirement.

No source age is declared fresh: EVIDENCE_CURRENT stays UNKNOWN. State confidence is not
forecast or decision confidence. Schema 002 and new audit enum subjects require matching
reader code; old v1-only readers may reject new event subject values. Existing v1 history
is preserved unchanged and generic historical assessments are never automatically promoted
to trusted receipts. Failed-attempt audit across infrastructure outage is not implemented.

The old broad `.env` package initializer, authentication placeholders and lifecycle/status
issues documented in 3A remain existing risks outside this increment. No production
application behavior or economic rule was changed to conceal them.

## 16. Recommended Increment 3C scope — design/review first

Review the assessment profile, source/coverage authority and supported operating semantics
before introducing production approval. Define versioned decision-policy/dependency/freshness
contracts with approval provenance, revocation and operation scope, keeping them separate
from diagnostic assessment configuration and all confidence axes. Resolve how assessment
profile references coexist with decision-policy references without breaking v1 history.

Founder decisions: source authority/methods and independence; canonical identities/units/
locations; stock count boundary/calendar rules; source completeness and coverage; supported
conversion/usage basis; policy ownership/approval/versioning; decision-specific freshness
and expiry; real baseline and migration procedures; identity provisioning; audit/deployment
controls. Do not invent these values or enable ALLOW. Review schema evolution and hosted
integration before any rollout. No 3C implementation was performed here.

## 17. Final repository status and stop

```text
 M app/evidence_contracts/audit.py
 M app/evidence_store/migration.py
 M app/evidence_store/repository.py
?? app/evidence_store/sql/002_inventory_assessments.sql
?? app/inventory_assessment/
?? docs/dr01-increment-3b.md
?? tests/inventory_assessment/
?? tests/postgres/test_inventory_assessment.py
```

Baseline preservation commits remain intact and HEAD is unchanged. All changes remain
uncommitted and unstaged. No branch/workspace switch, merge, reset, rebase, commit, push,
deployment, production import or production migration occurred. No implementation of a
recommendation gateway, seven business policies, cache invalidation or authorization
publication/execution paths was added.

The new receipt/adapter proves a narrower assessment boundary, not production permission.
STOP for founder review. Increment 3C/3D/3E require separate explicit approval.
