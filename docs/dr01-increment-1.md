# DR-01 Increment 1: evidence contracts and validation

## Scope and verified baseline

Implementation branch: `development/dr01-evidence-contracts-v1`.
Baseline: `development/dr01-economic-gate-assessment`, identical to
`integration/dr-01-pytest` at `3f66a088f6a82f21aff76a06b6818fe13536a4df`.
The integration worktree was clean before branch creation. The assessment
branch was not edited. No remote push, deployment, migration or commit is part
of this increment.

This increment adds contracts only. It does **not** secure current production
recommendation paths. No new code is imported into those paths, and their
existing behavior is unchanged. All existing DR-01 and economic calculations
remain unchanged, including the separately recorded waste term.

## Repository and entry-point audit

The audit inspected application source, ORM models, routers, background jobs,
DR-01/Economic Engine libraries, and the regression suite before implementation.

| Entry point | Existing call path | Current risk / later enforcement point |
| --- | --- | --- |
| `POST /run-analysis` | `api.routes.post_run_analysis` -> `run_analysis(1)` -> `run_all_rules` | Fixed tenant 1; no reliability gate; populates process-global cache |
| `POST /run-analysis/{restaurant_id}` | `api.analysis.post_run_analysis` -> `run_full_analysis` -> `run_all_rules` -> priority sort -> JSON log | Caller-selected tenant; no authentication dependency or reliability gate |
| `POST /analysis/run-analysis/{restaurant_id}` | Same analysis router mounted under `/analysis` in `api.routes` | Alternate URL bypass if only the top-level route is changed |
| `GET /recommendations` | Returns `_last_analysis_results` directly | No tenant, evidence revision, freshness or authorization binding |
| `POST /data/pos` | Authenticated ingestion -> commit -> FastAPI background `run_full_analysis` | API key restricts ingestion tenant; it does not certify evidence or resulting recommendations |
| `POST /data/inventory` | Authenticated upsert -> commit -> background `run_full_analysis` | Latest item-name value overwrites prior inventory; no reconciliation history |
| `POST /data/labor` | Authenticated upsert -> commit -> background `run_full_analysis` | Ingestion is not labor evidence verification |
| `POST /data/sync` | Authenticated combined ingestion -> commit -> background `run_full_analysis` | Partial source coverage is not assessed |
| `analysis_service.run_analysis` | Opens session -> `run_all_rules` | Direct Python caller can bypass an HTTP-only gate |
| `analysis_service.run_full_analysis` | Rules -> sort -> `log_analysis_run` | Logs can publish actionable outputs even if a response is later blocked |
| `analysis_service.get_latest_recommendations` | Recomputes rules, sorts, catches exceptions and returns None | It is not just cache retrieval; errors must not be mistaken for eligibility success |
| `analysis_service.run_background_analysis` | Thread -> `run_full_analysis`, catches/prints exceptions | Failure handling currently hides failures from callers |
| `rules.engine.run_all_rules` and public rule functions | Direct SQL queries -> waste/low-sales/labor messages | Pure/direct invocation remains available; future separation of diagnostic calculation and authorized publication is essential |
| `EconomicDecision(...)` | Mutable dataclass construction | No stable first-class decision ID or evidence dependencies |
| `EconomicEngine.complete_cycle` | Creates measurement -> verifies compliance/quality -> learning -> mutates decision if executed | No DR-01 gate; caller-supplied executed flag; assigns VERIFIED for all executed cycles even with weak outcome verification |
| `verify_outcome`, `create_learning` | Direct library calls | Outcome verification is distinct from input eligibility; these are not protected operational boundaries |

There are no implemented proposal acceptance or operational execution API
endpoints/jobs. ACCEPTED/EXECUTED exist as enum states; `complete_cycle` records
claimed execution rather than dispatching an operational action. Logging and
HTTP responses are the existing publication surfaces. All current routes remain
as above in this increment; none are represented as gated.

### Existing data models

`Sales`: row ID, restaurant ID, sale date, item name, quantity sold and Float
revenue. `Inventory`: row ID, restaurant ID, item name, current stock and Float
unit cost. `Labor`: row ID, restaurant ID, date, hours and Float labor cost.
No evidence, snapshot, verification, audit or authorization tables exist. There
is no evidence-revision storage, trusted verifier registry or migration framework
introduced here. Existing database data was not read or migrated.

The ORM lacks inventory beginning balances, movement history, normalized item
units, physical-count provenance, observation timestamps and source completeness.
It cannot produce verified DR-01 snapshots by itself. Never backfill these gaps
with zero or the import timestamp.

### Existing tests

The baseline has 239 passing cases plus one disabled external-auth test. It
covers legacy API/ORM behavior, Economic Engine v1, DR-01 equations, reliability
states, required quantities, contradictory variance, and isolated test setup.
The new tests add contract validation without altering any existing assertions.

## Implemented contracts

New module: `app.evidence_contracts`. Uses existing Pydantic 2; no dependencies
were added. Contracts forbid extra fields and coercive Python input, are frozen,
and use immutable nested tuples/models. All five records require schema_version
`1.0.0`. Unsupported/missing schema versions fail validation. IDs are explicit,
tenant IDs/revisions are strictly positive integers (not booleans), and opaque
identifiers are nonblank and bounded. Timestamps require an explicit timezone
and normalize to UTC; unknown observation times remain None.

Policy/manifest references require an explicit identifier and numeric
major.minor.patch version. This validates their *shape*, not their existence.
No operational policy/manifest registry or freshness threshold is invented.
All ALLOW eligibility records are rejected, even with syntactically valid or
caller-fabricated references. Future gateway resolution is required to support
operational allow results; the record fields already carry their required scope.

### 1. EvidenceRecord

Contains schema version, tenant/item/unit/period scope, immutable evidence ID and
revision, domain/kind, explicit quantity semantics, source lineage, optional
observation/source-recording times, ingestion time, correction reference,
optional migration lineage and quality flags.

Quantity semantics:

- OBSERVED requires an explicit finite Decimal. Observed zero is valid.
- UNKNOWN has no value and carries an explicit missing-quantity flag.
- NOT_APPLICABLE has no value and requires a documented versioned rule reference.
  A rule reference is not proof that the rule is approved; later policy resolution
  must establish applicability. It is never silently treated as zero.
- Inventory quantities are nonnegative except signed adjustments.

Only physical observations with item/unit identity may be labelled inventory
observations. Legacy claims may retain unresolved identity/unit with matching
quality flags. Missing observation time/provenance requires corresponding flags;
no fallback to ingestion time occurs. Legacy claims require original table/row
and migration-batch references and explicit legacy/unverified flags. Numeric
precision loss or invalid legacy values must remain in a future raw artifact;
they must not be silently normalized into certified observations.

Evidence source records always retain UNVERIFIED intake status. They cannot
self-assert verified status. VerificationReference is a separate revision-bound
reference with issuer and purpose; it must be resolved/authenticated by future
trusted storage. Evidence corrections require the immediately preceding revision
of the same evidence and tenant. Checking that the predecessor actually exists
and serializing concurrent corrections are persistence responsibilities.

### 2. EvidenceSnapshot

Contains scope, policy reference, assembly time, exact evidence records/revisions
and separate verification references. Repeated identities or mixed revisions of
one identity, cross-tenant entries and verification links to other revisions are
rejected. Item/unit and explicit period boundaries must agree with snapshot
scope. Records cannot be ingested after snapshot creation.

SHA-256 covers the canonical contents, including provenance, policy, scope and
assembly time. Ordering of record/reference collections does not affect the
digest. Decimal serialization is exact and independent of arithmetic precision;
equivalent numeric representations and timezone offsets canonicalize equally.
Snapshot UUID is derived from the digest. Supplied digests/IDs must match content.
Changes to evidence revisions change the binding. Empty snapshots are allowed
to represent missing evidence, not as a basis for operational authorization.

A digest proves integrity of represented content, not accuracy, verifier trust,
source coverage or freshness. Re-sealing modified content makes a *new* snapshot,
not permission to reuse an old eligibility result.

### 3. ReliabilityAssessment

Separate from the legacy DR-01 dataclass; includes assessor identity, domain,
scope, snapshot bindings, policy/version, assessment time, state/confidence,
structured checks/reasons/actions, verification requirement and inventory result
quantities. An ineligible record requires reasons, actions and verification.
An eligible inventory assessment requires all mandatory checks to pass, HIGH
confidence, RELIABLE state, no blockers, finite nonnegative counts, a physical
count, and independently consistent zero variance. Noninventory eligibility is
not implicitly certified by inventory rules.

Source/count/coverage checks require separate verification references of the
right purpose. Checks can be unknown/failed; such records must explain why.
A documented NOT_APPLICABLE check does not pass a mandatory inventory check.

These are *assessment result records*, not authenticated authorization tokens.
A constructed eligible assessment cannot grant an operation. Its references and
assertions require trusted resolution in later increments; only structural and
internally checkable invariants are validated now.

### 4. DecisionEligibility

Contains issuer, eligibility/decision IDs, tenant/item/period scope, decision
type, exact requested operation, versioned dependency manifest, exact snapshot
and assessment bindings, policy/version, evaluation/optional expiry, outcome,
reasons, actions and mandatory revision/revocation invalidation conditions.
Assessment policy/digest bindings cannot be swapped to other snapshot references.
No global trusted flag exists. Denials may have missing evidence references so
they can represent missing-input/policy failures accurately.

**All ALLOW results are blocked in Increment 1.** No production policies,
resolver or service gateway exist. Denial reasons can explicitly record stale,
revoked, unknown-policy/manifest, tenant/revision or assessment failures. No
universal TTL is assigned. An explicitly supplied expiry must follow evaluation.
Recording invalidation conditions does not implement live revocation or resolve
concurrent writes; those behaviors need storage and gateway transactions.

### 5. AuditEvent

Contains event/stream IDs, sequence, tenant, actor identity/type, action, subject,
UTC time, exact evidence/snapshot/verification references, structured reasons
and predecessor/current integrity digests. Denial/revocation/invalidation needs
reasons. Verification events require a separate matching verification reference.
Evidence/snapshot subjects must identify the referenced revision/digest.

Frozen events and validate_audit_chain detect tampering, repeated event IDs,
reordering, skipped sequence, wrong predecessor, mixed streams/tenants and
backwards time. This is an in-memory append-only *contract*, not a durable audit
store or signature. A future repository must atomically assign sequence numbers,
prevent UPDATE/DELETE, authenticate writers and protect retained history. Hashes
alone cannot prevent a privileged actor rewriting a complete chain.

### Trust boundary and serialization

Use validated constructors/model_validate/model_validate_json at boundaries.
Pydantic model_construct/model_copy(update=...) and Python object-level escape
hatches bypass validation by design; they are not accepted capabilities. Audit
chain validation revalidates event payloads. A later gateway must revalidate and
resolve stored records, never trust caller-created eligible/verified objects.
No public intake endpoint accepts these records in this increment.

## Implementation versus future enforcement tests

Focused tests cover each record, strict versions/types/timezones, missing/zero/NA
semantics, legacy claim lineage, corrections, tenant separation, exact revision
and digest bindings, canonicalization, deep immutability, assessment consistency,
verification-reference purposes, policy-unavailable denials for every operation,
and audit integrity/order. Existing regressions run unchanged on both supported
dependency configurations.

The requested end-to-end behaviors for live revocation, stale-policy evaluation,
concurrent updates, background/legacy bypass prevention and idempotent migration
are **not implemented or claimed** here. Contract binding/rejection tests prepare
those interfaces; they do not substitute for repository/gateway integration tests.

## Founder decisions before operational authorization

- Approve domain-specific dependency manifests and supported policy versions.
- Define verifiers, authority boundaries, source-completeness checks and revocation.
- Define freshness windows by domain/operation and authoritative clock/periods.
- Approve item/unit mapping and documented not-applicable rules.
- Specify how operational failures/blocked outputs are represented to API clients.
- Resolve Economic Engine executed-versus-verified status semantics separately.

## Recommended Increment 2

Review the existing PostgreSQL schema and migration tooling first. Introduce
append-only evidence revisions, separate trusted verification records,
snapshots/assessment references and audit streams with tenant foreign keys,
unique revision/event/sequence keys, optimistic concurrency and transactional
supersession/revocation. Do not add a permissive legacy fallback or execute a
production migration as part of design work.

Test repository isolation, history preservation, unauthorized verification,
concurrent corrections, audit ordering, idempotent ingestion and transactional
invalidation. Existing rows should remain unverified claims with explicit gaps;
no receipts, counts, observation times, units or source completeness are invented.
Production policies/gateway enforcement and actual legacy import remain later
increments with explicit approval and migration review.

## Verified results

Executed the complete suite after the final code change:

| Configuration | Passed | Failed | Skipped | Errors | Warnings |
| --- | ---: | ---: | ---: | ---: | ---: |
| Installed | 375 | 0 | 1 | 0 | 8 |
| Older compatible | 375 | 0 | 1 | 0 | 16 |

This includes all 239 pre-existing passing regressions plus 136 new contract
cases. The skip is the existing disabled live Supabase authentication test.
Both environments pass pip check. Existing dependency/application deprecation
warnings remain visible. No live external verification or PostgreSQL persistence
is implied by these results.

Commands, from `/workspace/RORI-integration`:

```bash
/workspace/RORI/.venv/bin/python -m pytest -q --tb=short --junitxml=/workspace/rori-contracts-current.xml
/tmp/rori-compat-venv/bin/python -m pytest -q --tb=short --junitxml=/workspace/rori-contracts-compat.xml
/workspace/RORI/.venv/bin/python -m pip check
/tmp/rori-compat-venv/bin/python -m pip check
```

The compatibility environment uses tests/constraints/compat.txt (FastAPI 0.115,
Pydantic 2.10, pytest 8 and the older compatible dependency stack). The installed
stack uses FastAPI 0.158.1, Pydantic 2.14.1 and pytest 9.1.1. JUnit files are
outside the repository. Source diff checks confirm that all existing application
modules, business rules and existing tests are unchanged. Only the new contract
package, tests/contracts and this document were added. No code was staged,
committed or pushed.
