# DR-01 Increment 3B hardening review

## 1. Executive verdict

**Recommendation: revise 3B before architectural advancement.** Three reproduced
implementation defects have narrow corrections and regression tests. The local
deny-only assessment implementation can be reviewed on that basis, but coverage
attestation versus independently established completeness needs an explicit,
machine-readable contract decision before downstream consumers may rely on it.
Changing existing persisted coverage-check semantics is deferred for founder
approval. No new migration or historical payload rewrite was made.

This review does not authorize production use, begin 3C/3D/3E, or establish that
real inventory observations or external source streams are accurate or complete.
All operational eligibility remains false. Passing tests establish the tested
local behavior, not production readiness.

Evidence labels in this report:

* **Tested:** executed against actual local PostgreSQL 15 or an independent arithmetic oracle.
* **Reviewed:** source/SQL inspection, not proof of a deployed control.
* **Unverified:** hosted systems, external source truth or unexecuted deployment behavior.
* **Decision required:** semantics that cannot safely be chosen by engineering alone.

## 2. Repository preflight and preservation

Repository: `/workspace/RORI-integration`.
Branch: `development/dr01-evidence-contracts-v1`.
Baseline and final HEAD: `725c7d51e679a597014df7d48d55566ff6e9fb10`.
Origin fetch/push configuration: `https://github.com/marcuslindsay41-afk/RORI.git`.
No fetch or push was needed for this local review; remote currentness was not
reasserted from the configured URL alone.

Preservation commits remain intact:

* `6ab031f9ba8349417aa08a8b8dd21a52356a5457` — evidence contracts.
* `725c7d51e679a597014df7d48d55566ff6e9fb10` — evidence persistence.

The index was empty. The exact 13 pre-existing uncommitted 3B files matched
`/workspace/rori-3b-tested-source-fingerprints.json` byte for byte. A separate
pre-edit SHA-256 inventory was saved at
`/workspace/rori-3b-hardening-preflight.json`. The working tree matched the prior
report; no conflicting commit or unrelated source edit was found.

SQL 001 remains SHA-256
`bf113273fd0d9d9caf08a32b18b75b8e4e7732febcb663590f46069e823d00ad`.
SQL 002 remains SHA-256
`b01380e368d4b2209f6972eb8ea4687d29a3a586a431331dac7523973af922af`.
Neither SQL file changed in hardening. The historical 3B report is preserved;
this report supersedes its claims about complete PASSED checks and qualified
verifications. Existing contracts, application routes, economic functions,
reconciliation and reliability functions, tests and fixtures are preserved.

The former `/tmp` database configuration and older virtual environment were
absent after environment resumption. Their absence was environmental, not source
drift. A fresh PostgreSQL 15 tmpfs Docker container, synthetic credentials and
loopback-only connection were provisioned with the unchanged helper. Test setup
never loaded the real `.env` or used application database settings. No production
database, tenant, source integration or live Supabase authentication was accessed.

## 3. Findings ranked by severity

| Severity | Finding | Status / evidence |
|---|---|---|
| Critical | No new critical bypass reproduced within the 3B adapter boundary | This is not a security claim about the unchanged recommendation application. |
| High | Missing closing count could yield aggregate SOURCE_VERIFIED, COUNT_VERIFIED and COVERAGE_COMPLETE PASSED checks using partial references | Fixed in `adapter._assess`; regression originally failed. |
| High | Opaque verification limitations were ignored, allowing qualified evidence to produce RELIABLE, REVIEW_REQUIRED or UNRELIABLE calculations | Fixed: unresolved limitations block numerical reconciliation; original three state tests failed. |
| High | COVERAGE_COMPLETE/PASSED expresses a verified attestation but does not establish external source completeness | Reproduced omission. Semantic clarification/evolution requires approval; no silent reinterpretation of stored checks. |
| High, pre-existing production blocker | Recommendation APIs, direct services, background jobs and caches remain outside the adapter | Reviewed; unchanged and explicitly outside 3B. No operational gateway is claimed. |
| Medium | Correct migration ledger could conceal missing v2 functions/tables and repeated install reported success | Fixed by read-only required-object presence checks; no schema repair or migration change. |
| Medium | Current issuer authority is actor-wide and depends on mutable present-day grants, not a versioned historical authority record | Tested ordinary access loss, capability loss/restoration, replacement login and explicit revocation. Governance decision required. |
| Medium | Authorized generic SQL can persist semantically invalid manifests; schema-owner/DBA remains trusted | Tested: adapter rejects malformed stored payload. SQL is not a complete Python contract validator. |
| Medium | Hosted role ownership, RLS deployment, pooling identity and live Supabase behavior remain unverified | Local superuser-owned schema is not proof of hosted security. |
| Medium | Ledger checks and new presence checks do not attest function bodies, trigger/policy definitions or ACL drift | Reviewed limitation; deployment catalog attestation remains required. |
| Low | Closed v1 audit subject readers cannot parse new 002 subject values | Tested; coordinated reader rollout remains required. |
| Low | Existing application/dependency deprecations remain | Counted separately; no warning filters or suppression added. |

## 4. Reproductions and corrections

### H1 — partial verification presented as aggregate success

`app/inventory_assessment/adapter.py::_assess` deliberately permits a numerical
diagnostic when only the closing count is missing. It constructs InventoryRecord
with physical_count=None and calls the original domain functions. Previously,
the presence of any result and nonempty verification reference lists was enough
to emit aggregate PASSED checks. Opening-count verification was incorrectly
presented as COUNT_VERIFIED for the entire dependency set; source/coverage checks
also omitted the absent closing dependency.

Before correction, `test_missing_closing_count_cannot_claim_complete_verification`
failed on actual PASSED checks. After correction the numerical diagnostic remains
available, but none of the aggregate verification checks is emitted for this
partial-input case. This preserves expected inventory=85 without manufacturing
an actual count or variance. A separate regression preserves the domain's
negative-expected UNRELIABLE diagnostic when closing count is absent, also with
no PASSED checks.

Minimal correction: the existing PASSED-check branch additionally requires
`not closing_only_missing`. Complete, authenticated source/count attestations can
still pass independently of nonzero arithmetic variance or a negative expected
result. A count attestation and a reconciliation result answer different questions.

### H2 — qualified verification silently treated as unconditional proof

Persisted VerificationRecord already has `limitations`. The resolver checked full
shape, issuer, method, purpose, scope, currentness and references, but `_assess`
ignored this field. A source record with `limitations=('quantity-not-verified',)`
produced each of the three complete numerical states depending on quantities.

Before correction, all three `state_input` regressions failed: RELIABLE,
REVIEW_REQUIRED and UNRELIABLE were returned where validated dependency support
was insufficient. Correction adds the structured block code
`verification_limitations_unresolved` / UNVERIFIED_EVIDENCE for any nonempty
limitations. These identifiers have no approved executable exception semantics;
engineering cannot determine that one is harmless. No values are fabricated and
the original verification remains immutable and auditable.

Expanded regressions exercise SOURCE, COUNT and COVERAGE limitations in all three
quantity scenarios. All return INCOMPLETE, no numerical result and no PASSED
verification checks. This is intentionally conservative even if a future approved
limitation vocabulary permits some qualified diagnostics.

### M1 — migration success with missing required objects

`app/evidence_store/migration.py` previously accepted a correct v1+v2 checksummed
ledger without checking whether required v2 objects still existed. On a separate
disposable database, dropping `assessment_context(bigint)` then invoking
`install_assessments()` returned success. The new expected-rejection test failed
with DID NOT RAISE ValueError before the correction.

`_require_assessment_objects(connection)` now checks presence of the three v2
relations and four function signatures. It runs for accepted v2 ledgers and after
new v2 creation, inside the existing migration transaction/lock. Missing objects
raise `ValueError('Incomplete assessment schema; explicit administrative review
required')`. No object is recreated, no ledger is rewritten and no history is
changed. Seven regression variants remove each required object independently.
This checks presence, not complete catalog equivalence or resistance to a malicious DBA.

### Before/after evidence and test development

* Unchanged baseline full suite: 513 passed, 1 skipped, 0 failures/errors, 8 warnings.
* First adversarial file before adapter correction: **4 failed, 13 passed,
  0 skipped/errors, 5 warnings**. JUnit: `/workspace/rori-3b-hardening-before.xml`.
* Initial corrected adapter/arithmetic subset: **28 passed, 0 failed/skipped/errors,
  5 warnings**. JUnit: `/workspace/rori-3b-hardening-after.xml`.
* Migration regression before installer correction: **1 failed, 0 passed/skipped/errors,
  5 warnings**. JUnit: `/workspace/rori-3b-hardening-migration-before.xml`.
* Migration/SQL file after correction, before seven-way expansion: **12 passed,
  0 failed/skipped/errors, 5 warnings**. JUnit:
  `/workspace/rori-3b-hardening-migration-after.xml`.

During new test development, two SQL-test failures were harness mistakes: expecting
SQLAlchemy DBAPIError when the explicit migration cursor raises psycopg2 DuplicateTable,
and invoking Git after the existing fixture changes cwd to a temporary directory.
The exact exception assertion was corrected, and the historical enum probe now uses
the frozen seven v1 values without requiring Git at runtime. Three further failures
in expanded coverage-limitation tests were caused by replacing a verification reference
without updating the manifest claim; the helper now appends a new correctly bound
manifest. Application checks were not relaxed. All those cases are included in final
passing runs. No old tests, assertions or skips were changed.

## 5. Numerical-precondition classification — all adapter block codes

Categories are operationally distinct:

* **P:** precondition failure prevents numerical reconciliation entirely. Output
  INCOMPLETE, confidence UNKNOWN, quantities None, no aggregate PASSED checks.
* **D:** supported partial diagnostic: expected inventory only, actual/variance
  unknown; no aggregate PASSED checks. Domain still classifies negative expected
  inventory UNRELIABLE/LOW, otherwise INCOMPLETE/UNKNOWN.
* **R:** calculated result/review condition, discovered by unchanged domain formula.
  Quantities remain diagnostic, confidence follows unchanged domain evaluator.
* **O:** operational authorization blocker; does not invalidate validated numerical
  calculation. Never permits operational eligibility.

Every pre-calculation detail blocks computation except the sole D condition.
Two or more defects cannot cancel each other or activate that exception. Invalid
or missing persisted contracts, stale/revoked evidence, unauthorized DB identities,
bad digests and infrastructure failures raise typed errors rather than these blocks.

| Block code | Class | Rationale |
|---|---|---|
| incomplete_scope | P | Unknown item/unit/period cannot define inventory inputs. |
| assessment_profile_unapproved_or_unavailable | P | No executable approved synthetic assessment semantics. |
| manifest_unavailable | P | No resolved dependency/coverage plan. |
| location_scope_not_supported | P | Scope cannot be represented by supported profile. |
| snapshot_policy_profile_mismatch | P | Snapshot configuration is not the exact selected profile. |
| unit_profile_mismatch | P | No canonical compatible unit. |
| legacy_claim_cannot_supply_inventory | P | Claims or legacy ancestry are not certified observations. |
| record_scope_or_period_mismatch | P | Exact tenant/item/unit/period binding absent. |
| observation_time_unknown | P | Unknown observation cannot establish period/count boundary. |
| verification_method_or_issuer_unapproved | P | Authenticated issuer is not sufficient without profile authority/method. |
| verification_limitations_unresolved | P | Qualified support cannot prove unconditional prerequisites. |
| missing_opening_count | P | No beginning inventory. |
| missing_physical_count | D if sole defect, otherwise P | Validated opening/movements permit expected-only diagnostic; no actual count invented. |
| missing_receipt | P | Missing receipts coverage is not zero. |
| missing_theoretical_usage | P | No validated waste-exclusive usage. |
| missing_recorded_waste | P | Missing waste stream is not zero. |
| missing_transfer_in | P | Missing incoming movement stream is not zero. |
| missing_transfer_out | P | Missing outgoing stream is not zero. |
| missing_adjustment | P | Missing signed adjustment coverage is not zero. |
| competing_or_overlapping_opening_count | P | Ambiguous opening stream. |
| competing_or_overlapping_physical_count | P | Ambiguous closing stream. |
| competing_or_overlapping_receipt | P | Ambiguous/overlapping receipts coverage. |
| competing_or_overlapping_theoretical_usage | P | Ambiguous/overlapping usage coverage. |
| competing_or_overlapping_recorded_waste | P | Ambiguous/overlapping waste coverage. |
| competing_or_overlapping_transfer_in | P | Ambiguous/overlapping incoming coverage. |
| competing_or_overlapping_transfer_out | P | Ambiguous/overlapping outgoing coverage. |
| competing_or_overlapping_adjustment | P | Ambiguous/overlapping adjustment coverage. |
| coverage_scope_mismatch | P | Coverage does not certify requested period/scope. |
| source_authority_unapproved | P | Source system not in selected profile. |
| unit_conversion_unresolved | P | No approved conversion lineage; no inferred factor. |
| usage_may_double_count_waste | P | Usage basis not established as waste-exclusive. |
| coverage_source_system_mismatch | P | Coverage proof and claim disagree on source. |
| coverage_source_not_verified | P | Coverage artifact lacks separate source attestation. |
| coverage_record_carries_unclassified_quantity | P | Coverage artifact cannot hide numerical movement. |
| not_applicable_rule_unapproved | P | No documented approved neutral mapping. |
| duplicate_evidence_reference | P | Same input would be counted twice. |
| missing_or_competing_count | P | Requires one boundary count, not a selected convenient value. |
| contradictory_no_movement_statement | P | Empty/zero claim contradicts events or count role. |
| empty_stream_without_no_movement_statement | P | Empty collection is not certified absence of movements. |
| overlapping_aggregate_and_events | P | Aggregate cannot overlap individual movements. |
| overlapping_dependency_inputs | P | Revision reused across dependencies. |
| missing_or_duplicate_source_event | P | Missing or duplicate canonical source identity. |
| source_or_role_mismatch | P | Event does not belong to role/source. |
| observation_outside_role_period | P | Wrong count boundary or movement outside [start,end). |
| unknown_or_not_applicable_quantity | P | Unknown and unsupported N/A are never zero. |
| unverified_source | P | Event lacks exact scoped SOURCE verification. |
| unverified_count | P | Count lacks exact scoped COUNT verification. |
| unassigned_or_competing_inventory_records | P | Quantitative snapshot observations omitted from plan. |
| unassigned_source_observation | P | Unexplained source artifact in snapshot. |
| evaluation_precedes_snapshot | P | Snapshot/evidence not available at fixed evaluation-as-of. |
| evaluation_precedes_verification | P | Verification not available at evaluation-as-of. |
| production_authorization_policy_unavailable | O | Always added; calculation configuration is not operational approval. |
| nonzero_unexplained_variance | R | Existing domain REVIEW_REQUIRED/LOW; discrepancy retained exactly. |
| negative_expected_inventory | R | Existing domain UNRELIABLE/LOW, variance unknown. |

These are all emitted string codes, including all eight expansions of the two
role-code families and both supported verification-purpose expansions. There is
no `unverified_coverage` block: a missing/invalid manifest coverage binding is an
explicit AssessmentIntegrityError instead.

Complete, attested, exact-zero synthetic inputs yield RELIABLE/MEDIUM under the
existing evaluator because freshness remains unverified; it is not a prediction
confidence or decision confidence. Nonzero variance yields REVIEW_REQUIRED/LOW;
negative expected inventory yields UNRELIABLE/LOW. No confidence formula, variance
tolerance or business threshold changed. The theoretical-usage basis remains
explicitly waste-exclusive and the original eight-role equation is called, not
reimplemented in production adapter code.

## 6. Coverage attestation versus independently established completeness

Tested omission construction:

1. Persist a complete synthetic snapshot, verifications and manifest.
2. Add another receipt to an independent synthetic source ledger, represented in
   the test by a valid persisted receipt outside the snapshot/manifest.
3. Assess the original exact immutable snapshot.
4. The extra receipt is not in provenance. Expected inventory remains 85 and the
   state remains RELIABLE relative to the attested collection. Eligibility is false.

The adapter checks identity, scope, period, source event deduplication, role
coverage and signed references within the selected collection. It cannot determine
what an external POS, receiving system or physical ledger contained but did not
export. Searching all evidence rows would not solve this: the external event may
never have been imported, unrelated records can coexist, and the immutable snapshot
is the reproducible input set.

What the implementation proves locally is that an authorized current verifier
attested an exact closed coverage statement with separate source support. It does
not prove actual external stream completeness, independent physical accuracy,
external artifact authenticity or source-export integrity. The recorded `stream_id`
is an attested identifier, not an authenticated connector identity or external
high-water mark.

**Unresolved machine-readable ambiguity:** existing COVERAGE_COMPLETE/PASSED has
no evidence-assurance axis separating a validated completeness attestation from
independently established completeness. Likewise SOURCE_VERIFIED and COUNT_VERIFIED
attest authorized records; no external artifact is fetched or independently
checked by this adapter. RELIABLE is snapshot-relative arithmetic, not absolute
truth. No consumer may interpret those labels as operational approval.

Changing this persisted meaning, adding assurance levels or replacing the check
requires explicit contract approval. That portion is stopped here. Recommended
review choice: distinguish `coverage_attested` from independently verified source
coverage and require the latter for future operational policies; until then retain
deny-only production behavior. An alternative is explicitly profile-scoped attested
coverage with separately mandatory external completeness prerequisites. Neither
alternative is silently implemented. No POS/source connector was added.

## 7. Historical versus current verifier authority and revocation

Tested and reviewed behavior of SQL 001/002:

| Event | Current assessment behavior | Historical behavior |
|---|---|---|
| Verification issuance | append_object requires authenticated actor and purpose capability, binds issuer and exact revision | Immutable record plus transactional audit retained. |
| Remove purpose capabilities | current_verification rejects with security error | Old assessment still retrievable. |
| Restore same actor capabilities | Identical current inputs can replay original receipt | No old row rewritten. |
| Disable issuer LOGIN | Other assessor can still resolve issued verification while principal_grants remains | LOGIN access and verification revocation are separate. |
| Give another login the same actor ID and purpose capabilities | Current actor-wide lookup accepts old issued verification | It is not bound to the original login's continuing employment. |
| Explicitly revoke verification | Reassessment and idempotent replay rejected | Historical evidence/assessment remains auditable. |
| Supersede verification or evidence | Old exact snapshot no longer current; assessment rejected | Old revisions remain available diagnostically. |
| Concurrent removal during assessment | Existing row locks hold authority stable through transaction | Reassessment after removal fails. |

Issuance-time capability is enforced at insertion, but there is no immutable,
versioned authority-grant history establishing why the authority was appropriate.
`verified_at` is supplied in the immutable verification contract and checked for
ordering; database creation/audit timestamps separately record persistence time.
Current grant evaluation occurs at assessment time even for fixed historical
evaluation-as-of. Thus deterministic arithmetic can be replayed from archived
inputs, but a trusted *current* replay can legitimately be denied after revocation
or authority change. Current denial does not erase historical calculation.

**Decision required:** decide whether ordinary employment/role loss invalidates
all earlier verifications, only bars future issuance, or requires separate
review. Decide how suspected fraud/compromise is represented and propagated.
Existing explicit revocation is available; no automated fraud determination or
retroactive certification was invented. A replacement actor grant must not become
a way to undo an explicit revocation. The tests establish this distinction.
No SQL authority/locking behavior was weakened or changed.

## 8. Migration and PostgreSQL security review

**Tested:** explicit v1-only initializer creates no v2 tables; explicit upgrade
creates a contiguous [1,2] ledger; repeat initialization/upgrade is idempotent.
Changed v1 or v2 checksum, unknown version and missing v1 ledger entry are rejected.
Unversioned existing schema is not adopted. A conflicting partial v2 relation
raises DuplicateTable; prior v1 ledger remains and earlier transactional DDL rolls
back. The new presence guard rejects missing required v2 objects without repair.

**Tested catalogs:** four new functions are SECURITY DEFINER, owned by the explicit
local schema administrator, with `search_path=pg_catalog, rori_evidence` and no
PUBLIC execution ACL. Three new tables have both RLS and FORCE RLS. Runtime logins
receive SELECT and specifically granted function execution; no direct INSERT.
Existing tests establish append-only UPDATE/DELETE/TRUNCATE protection and
cross-tenant reads/reference rejection. New tests confirm authenticated session_user
does not change when SET LOCAL ROLE changes current_user; tenant selection cannot
be switched by that mechanism.

**Reviewed limitations:** SECURITY DEFINER ownership must be a tightly controlled
schema role. The local installer uses a synthetic PostgreSQL administrator with
superuser privileges; FORCE RLS does not constrain superusers/BYPASSRLS. Schema
owners can change triggers, functions, grants or policies. Hashes and immutable-row
triggers do not defeat malicious administrators. PUBLIC is explicitly revoked,
but inherited memberships/default grants in a hosted deployment also require review.

`session_user` is the authenticated database login, not an HTTP restaurant ID or
JWT subject. A shared Supabase/PostgREST/pool login with SET ROLE cannot substitute
for reviewed tenant principal provisioning. No live hosted-role behavior, Supabase
token-to-principal bridge or real service identity was verified here.

**Direct SQL probe:** a write-capable authorized service can use the generic
put_inventory_manifest function to store an opaque invalid manifest with a forged
identity and malformed claims. This function's SQL checks are deliberately narrower
than full contracts. Adapter resolution revalidates and rejects the stored shape;
no trusted assessment is produced. Generic authorized SQL can also append blocked
assessment envelopes. A record's existence or decision_eligible=False does not
authenticate it as adapter-generated; trusted replay must resolve inputs and
recompute. Do not expose generic append functions to untrusted HTTP callers.

Old audit readers have a closed seven-value SubjectType enum; actual new
inventory_manifest/assessment_run events cannot be parsed by that enum. Deploy
matching readers before new event emission. No old audit event changed. Profile
admin provisioning still is not integrated into the runtime event hash chain;
authority/approval governance and its audit are unresolved production concerns.

## 9. Decimal correctness and determinism

No arithmetic defect was reproduced; `arithmetic.py` is byte-identical to preflight.
The test oracle uses Python Fraction, constructed directly from exact Decimal
inputs, and independently calculates the mathematical expected value and variance.
It does not ask exact_arithmetic to calculate its own expected test result.

New tests execute 500 deterministically seeded eight-role records under each of
four ambient precisions (1,3,28,100): **2,000 rational-oracle comparisons**. Inputs
vary coefficient/exponent, include signed adjustments and negative expected
results. Adversarial cases include cancellation across large exponents, 2,000-digit
coefficients, tiny fractions, all zeros, large positive/negative adjustments,
boundary precision and 10,001 repeated event additions. Unsupported spans,
exponents and nonfinite values reject explicitly. Existing tests cover process
DefaultContext changes, traps, high-precision adapter/receipt replay and reproducible
computation digests under different ambient contexts.

Reviewed headroom argument: let E be the minimum input exponent or zero, and H
the maximum nonzero adjusted exponent. All aligned coefficients occupy at most
H-E+1 positions. Summing n magnitudes needs at most ceil(log10(n)) carry digits;
subtraction/cancellation cannot exceed that magnitude bound. The implementation
reserves len(str(n+8))+2 digits beyond the maximum span/coefficient length. For the
eight-role equation this exceeds the required carry headroom for intermediate
seven-input expected inventory and actual-minus-expected variance. Event aggregation
also reserves based on its full event count. All relevant signals trap; rounding
never silently converts a nonzero variance to zero. Resource bounds of 4096
precision/exponent are conservative implementation limits, not business thresholds.

This is a bounded reasoning argument plus adversarial tests, not a proof about
arbitrary arithmetic that callers might execute inside the generic context manager.
No multiplication, conversion or new economic formula was added.

## 10. Test commands and exact results

All database tests used disposable PostgreSQL 15 on loopback with synthetic
credentials at `/tmp/rori-3b-hardening-pg.json` (private mode-600 configuration).
The JSON contains credentials and must never be committed or printed.

```sh
env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
  DOCKER_HOST=unix:///var/run/docker.sock /workspace/RORI/.venv/bin/python \
  tests/postgres/provision.py /tmp/rori-3b-hardening-pg.json

/workspace/RORI/.venv/bin/python -m venv /tmp/rori-3b-hardening-compat
/tmp/rori-3b-hardening-compat/bin/python -m pip install \
  -r requirements-test.txt -c tests/constraints/compat.txt

RORI_EVIDENCE_TEST_CONFIG=/tmp/rori-3b-hardening-pg.json \
  /workspace/RORI/.venv/bin/python -m pytest -q --tb=short \
  --junitxml=/workspace/rori-3b-hardening-installed-final.xml

RORI_EVIDENCE_TEST_CONFIG=/tmp/rori-3b-hardening-pg.json \
  /tmp/rori-3b-hardening-compat/bin/python -m pytest -q --tb=short \
  --junitxml=/workspace/rori-3b-hardening-compat-final.xml

env -u RORI_EVIDENCE_TEST_CONFIG /workspace/RORI/.venv/bin/python -m pytest -q --tb=short \
  --junitxml=/workspace/rori-3b-hardening-disabled-final.xml

/workspace/RORI/.venv/bin/python -m pip check
/tmp/rori-3b-hardening-compat/bin/python -m pip check
```

Verified final results:

| Configuration | Passed | Failed | Skipped | Errors | Warnings |
|---|---:|---:|---:|---:|---:|
| Installed dependencies + real disposable PostgreSQL 15 | 568 | 0 | 1 | 0 | 8 |
| Older compatible dependencies + real disposable PostgreSQL 15 | 568 | 0 | 1 | 0 | 16 |
| Installed dependencies, PostgreSQL explicitly disabled | 435 | 0 | 134 | 0 | 8 |

The original 513 passing tests remain; **55 new passing tests** comprise 11
unit/arithmetic and 44 real PostgreSQL cases. Each enabled run includes **133 real
PostgreSQL tests** (89 existing plus 44 new). The enabled skip is the existing live
Supabase authentication test; the disabled run skips those 133 database cases plus
that external test. JUnit totals independently confirm 569 collected cases with
zero failures/errors. Runtime: 28.17s installed, 30.13s compatible, 3.18s disabled.

Warnings are existing FastAPI/Starlette/httpx, Pydantic min_items, passlib crypt,
datetime.utcnow and older Supabase/python-jose deprecations. They were neither
suppressed nor converted to test success. Both pip checks report no broken
requirements. Supabase authentication and hosted PostgreSQL remain unverified.

Final runs must be sequential when they share the same PostgreSQL schema. The
disabled configuration does not assert database correctness. Existing local tests
replace app configuration before imports, never load the real `.env`, isolate SQL
data and prohibit external service requests. No credentials were mocked as live
Supabase success. Both dependency environments passed pip check; only a pip-cache
permission warning was emitted by that tool.

## 11. Remaining limitations and required founder decisions

1. Approve machine-readable separation of coverage attestation from independent
   completeness; preserve existing archived semantics and version any evolution.
   This is the required next 3B contract clarification, not implementation of 3C.
2. Approve qualification vocabulary for verification limitations. Until then all
   nonempty limitations prevent trusted numerical assessment.
3. Define issuance authority, ordinary role loss, fraudulent/compromised verification,
   revocation, historical replay and identity-reuse governance; do not infer rules
   from mutable employment grants.
4. Independently authenticated source exports, proof artifacts, physical observation
   procedures, real verifier onboarding and coverage ownership are absent.
5. Production assessment policies, freshness, supported conversions/location/multiple
   stream rules, HTTP identity bridge and decision-operation gateway remain absent.
6. Review deployment ownership/ACL/catalog attestation and coordinated audit-reader
   rollout before applying 002 anywhere outside disposable test environments.
7. Existing recommendation, background, cache and outcome lifecycle weaknesses remain;
   no diagnostic result may be published as an authorized operational decision.

No new schema evolution, persisted coverage reinterpretation, production policy or
gateway implementation is proposed as automatically authorized by this review.

## 12. Changed-file inventory

Changes made **during hardening**, relative to the exact preflight 3B bytes:

| File | Hardening responsibility |
|---|---|
| app/inventory_assessment/adapter.py | Reject unresolved verification limitations; suppress aggregate PASSED checks on closing-only diagnostic. |
| app/evidence_store/migration.py | Read-only required-v2-object presence check; refuse incomplete provisioning. |
| tests/postgres/test_inventory_assessment_hardening.py | Verification combinations, missing closing count, limitations, omitted external transaction, authority changes/revocation. |
| tests/postgres/test_inventory_assessment_sql_hardening.py | Explicit upgrades, checksums/unknown ledgers, partial provisioning/rollback, object presence, privileges/RLS/SET ROLE, raw SQL and old-reader probes. |
| tests/inventory_assessment/test_arithmetic_hardening.py | Fraction oracle, seeded adversarial equations, exponent/carry/cancellation/boundary cases. |
| docs/dr01-increment-3b-hardening-review.md | This review, reproductions, classification, results and unresolved decisions. |

All pre-existing 3B checkpoint files remain present. The other eleven files are
byte-identical to preflight: `app/evidence_contracts/audit.py`,
`app/evidence_store/repository.py`, `app/evidence_store/sql/002_inventory_assessments.sql`,
`app/inventory_assessment/__init__.py`, `errors.py`, `arithmetic.py`, `contracts.py`,
`storage.py` (the last five under that same package),
`tests/inventory_assessment/test_contracts_and_arithmetic.py`,
`tests/postgres/test_inventory_assessment.py`, and `docs/dr01-increment-3b.md`.
The older report is historical, not rewritten to hide its original claim.

External review artifacts (outside the repository): preflight/final fingerprint
inventories, JUnit reports, synthetic private DB config, compatible dependency
environment/install log and the hardening review patch. Generated caches remain
ignored. No credential/environment/generated file was staged or included in source.

## 13. Final Git status and stopping boundary

HEAD and branch remain unchanged, with an empty index. All 3B work and all hardening
changes remain uncommitted and unstaged. There was no reset, rebase, stash, branch
switch, discard, commit, push, merge, deployment or production migration. Disposable
local schema changes performed by integration tests are the only database changes.

```text
 M app/evidence_contracts/audit.py
 M app/evidence_store/migration.py
 M app/evidence_store/repository.py
?? app/evidence_store/sql/002_inventory_assessments.sql
?? app/inventory_assessment/__init__.py
?? app/inventory_assessment/adapter.py
?? app/inventory_assessment/arithmetic.py
?? app/inventory_assessment/contracts.py
?? app/inventory_assessment/errors.py
?? app/inventory_assessment/storage.py
?? docs/dr01-increment-3b-hardening-review.md
?? docs/dr01-increment-3b.md
?? tests/inventory_assessment/test_arithmetic_hardening.py
?? tests/inventory_assessment/test_contracts_and_arithmetic.py
?? tests/postgres/test_inventory_assessment.py
?? tests/postgres/test_inventory_assessment_hardening.py
?? tests/postgres/test_inventory_assessment_sql_hardening.py
```

Only expected pytest/bytecode caches are ignored. Final review artifacts are
`/workspace/rori-increment-3b-hardening-review.patch` (complete uncommitted 3B diff,
including untracked source) and `/workspace/rori-3b-hardening-final-fingerprints.json`.
Final checks include unchanged SQL digests, unchanged original business/tests,
empty index, source syntax/whitespace checks and targeted secret-pattern review.

Implemented-and-tested: two adapter corrections, installer presence hardening,
adversarial/regression/security/arithmetic tests. Implemented but externally
unverified: the original hosted identity/role/source assumptions. Designed only:
the proposed coverage assurance and authority governance alternatives. Blocked or
deferred: persisted-semantic evolution requiring approval, source connectors,
production authorization, 3C/3D/3E and any deployment.

Stop for founder review. The reason to revise before advancement is explicit
coverage/authority semantics, not a need to change economic calculations or weaken
the deny-only boundary.
