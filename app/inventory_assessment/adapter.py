"""Deny-only adapter: existing DR-01 functions are the sole reconciliation engine."""
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from pydantic import TypeAdapter

from app.data_reliability.models import InventoryRecord, ReliabilityState
from app.data_reliability.reconciliation import reconcile_inventory
from app.data_reliability.reliability import (assess_reliability,
    ReliabilityAssessment as DomainReliabilityResult, EvidenceConfidence)
from app.evidence_contracts.common import (Identifier, Timestamp, VersionReference, VerificationPurpose,
    ReasonCode, VerificationAction, integrity_digest)
from app.evidence_contracts.evidence import EvidenceKind, EvidenceDomain, ValueState
from app.evidence_contracts.decisions import (ReliabilityAssessment as AssessmentEnvelope,
    EvidenceCheck, CheckKind, CheckStatus)
from app.evidence_store.repository import validated, EvidenceTransaction
from .contracts import (AssessmentRequest, TrustedAssessmentReceipt, CalculationProvenance,
    BlockDetail, ProfileStatus, Representation, ROLES, COUNTS, calculation_body)
from .arithmetic import exact_arithmetic
from .errors import AssessmentIntegrityError, AssessmentSecurityError
from . import storage

FIELDS = {EvidenceKind.OPENING_COUNT: 'beginning_inventory', EvidenceKind.RECEIPT: 'receipts',
    EvidenceKind.TRANSFER_IN: 'transfers_in', EvidenceKind.THEORETICAL_USAGE: 'theoretical_usage',
    EvidenceKind.RECORDED_WASTE: 'recorded_waste', EvidenceKind.TRANSFER_OUT: 'transfers_out',
    EvidenceKind.ADJUSTMENT: 'adjustments', EvidenceKind.PHYSICAL_COUNT: 'physical_count'}


def assess_inventory_snapshot(transaction, snapshot_reference, assessment_profile_reference,
                              request_scope, evaluation_context=None, idempotency_key=None, *,
                              manifest_id, manifest_digest):
    """Return a persisted TrustedAssessmentReceipt containing a blocked envelope.

    The manifest is a separate exact immutable dependency/coverage claim. Evaluation
    context is resolved from PostgreSQL and an admin-provisioned synthetic profile;
    caller-supplied clocks/flags are never accepted. No production-approved profile
    type exists in this increment. A savepoint rolls back adapter writes on failure;
    no misleading envelope is returned on integrity/security/DB failure.
    """
    if not isinstance(transaction, EvidenceTransaction):
        raise AssessmentSecurityError('TRUSTED_REPOSITORY_TRANSACTION_REQUIRED')
    if evaluation_context is not None:
        raise AssessmentSecurityError('CALLER_EVALUATION_CONTEXT_FORBIDDEN')
    key = TypeAdapter(Identifier).validate_python(idempotency_key, strict=True)
    request = AssessmentRequest(snapshot=snapshot_reference, profile=assessment_profile_reference,
                                scope=request_scope, manifest_id=manifest_id, manifest_digest=manifest_digest)
    request = validated(AssessmentRequest, request)
    if request.scope.restaurant_id != transaction.restaurant_id:
        raise AssessmentSecurityError('TENANT_MISMATCH')
    with storage.failures():
        transaction.require_repository_origin()
        with transaction.connection.begin_nested():
            return _assess(transaction, request, key)


def _assess(transaction, request, key):
    ctx = storage.context(transaction)
    snap = transaction.resolve_snapshot(request.snapshot)
    # Historical archive scopes may be incomplete; a different requested identity is not authorized.
    if snap.scope != request.scope:
        raise AssessmentIntegrityError('REQUEST_SNAPSHOT_SCOPE_MISMATCH')
    profile = storage.profile(transaction, request.profile)
    manifest = storage.manifest(transaction, request.manifest_id, request.manifest_digest)
    verifications = {v: storage.verification(transaction, v) for v in snap.verification_refs}
    records = {r.reference: r for r in snap.records}
    legacy_lineage = False
    for record in snap.records:
        # Currentness comes from resolve_snapshot; these reads authenticate exact stored content/history.
        if transaction.get('evidence', record.reference.evidence_id, record.reference.revision) != record:
            raise AssessmentIntegrityError('SNAPSHOT_STORED_EVIDENCE_MISMATCH')
        ancestor = record
        while True:
            if ancestor.kind == EvidenceKind.LEGACY_CLAIM or ReasonCode.LEGACY_CLAIM in ancestor.quality_flags:
                legacy_lineage = True
            if ancestor.supersedes is None:
                break
            ancestor = transaction.get('evidence', ancestor.supersedes.evidence_id, ancestor.supersedes.revision)
    details = set()
    def block(code, reason):
        details.add((code, reason))
    complete_scope = all(getattr(request.scope, field) is not None
                         for field in ('item_id', 'unit', 'period_start', 'period_end'))
    if not complete_scope:
        block('incomplete_scope', ReasonCode.UNKNOWN_PERIOD)
    if profile is None or profile.status != ProfileStatus.SYNTHETIC_TEST_APPROVED:
        block('assessment_profile_unapproved_or_unavailable', ReasonCode.POLICY_UNAVAILABLE)
    if profile is not None and profile.status == ProfileStatus.SYNTHETIC_TEST_APPROVED and ctx['database'] != 'rori_evidence_test':
        raise AssessmentSecurityError('SYNTHETIC_PROFILE_OUTSIDE_DISPOSABLE_DATABASE')
    if manifest is None:
        block('manifest_unavailable', ReasonCode.UNKNOWN_MANIFEST)
    elif manifest.scope != request.scope or manifest.snapshot != request.snapshot:
        raise AssessmentIntegrityError('MANIFEST_SCOPE_SNAPSHOT_MISMATCH')
    if manifest is not None and manifest.location_id is not None:
        block('location_scope_not_supported', ReasonCode.UNRESOLVED_ITEM)
    if profile is not None and snap.policy != VersionReference(identifier=profile.identifier, version=profile.version):
        block('snapshot_policy_profile_mismatch', ReasonCode.UNKNOWN_POLICY_VERSION)
    if profile is not None and profile.unit != request.scope.unit:
        block('unit_profile_mismatch', ReasonCode.UNRESOLVED_UNIT)
    if legacy_lineage:
        block('legacy_claim_cannot_supply_inventory', ReasonCode.LEGACY_CLAIM)
    for r in snap.records:
        if r.scope != request.scope:
            block('record_scope_or_period_mismatch', ReasonCode.UNKNOWN_PERIOD)
        if r.effective_at is None:
            block('observation_time_unknown', ReasonCode.UNKNOWN_OBSERVATION_TIME)
    # Every referenced verification is fully resolved even for incomplete inputs.
    for ref, value in verifications.items():
        if ref.evidence not in records:
            raise AssessmentIntegrityError('VERIFICATION_OUTSIDE_SNAPSHOT')
        observed = records[ref.evidence].effective_at
        if observed is not None and value.verified_at < observed:
            raise AssessmentIntegrityError('VERIFICATION_PRECEDES_OBSERVATION')
        if profile is not None and (value.issuer_id not in profile.verification_issuers
                                   or value.method not in profile.verification_methods):
            block('verification_method_or_issuer_unapproved', ReasonCode.UNVERIFIED_EVIDENCE)
        # Limitations are opaque identifiers, not approved exception rules. A
        # qualified attestation cannot establish an unconditional prerequisite.
        # Preserve the record; block until its limitations have reviewed semantics.
        if value.limitations:
            block('verification_limitations_unresolved', ReasonCode.UNVERIFIED_EVIDENCE)
        if value.verified_at > TypeAdapter(Timestamp).validate_python(datetime.fromisoformat(ctx['now'])):
            raise AssessmentIntegrityError('FUTURE_VERIFICATION')
    quantities = {}
    used = set()
    source_refs, count_refs, coverage_refs = [], [], []
    coverage_records = set()
    seen_sources = set()
    if profile is not None and manifest is not None and complete_scope:
        claims = manifest.claims
        for role in ROLES:
            choices = [c for c in claims if c.statement.role == role]
            if not choices:
                block('missing_'+role.value, ReasonCode.MISSING_COUNT if role in COUNTS else ReasonCode.MISSING_MOVEMENT_COVERAGE)
                continue
            if len(choices) != 1:
                block('competing_or_overlapping_'+role.value, ReasonCode.MISSING_MOVEMENT_COVERAGE)
                continue
            claim = choices[0]
            statement = claim.statement
            if statement.scope != request.scope:
                block('coverage_scope_mismatch', ReasonCode.UNKNOWN_PERIOD)
                continue
            if statement.source_system not in profile.source_systems:
                block('source_authority_unapproved', ReasonCode.UNVERIFIED_EVIDENCE)
            if statement.unit_basis != profile.unit_basis:
                block('unit_conversion_unresolved', ReasonCode.UNRESOLVED_UNIT)
            if role == EvidenceKind.THEORETICAL_USAGE and statement.usage_basis != profile.usage_basis:
                block('usage_may_double_count_waste', ReasonCode.MISSING_PROVENANCE)
            if claim.verification not in verifications:
                raise AssessmentIntegrityError('COVERAGE_VERIFICATION_NOT_BOUND_TO_SNAPSHOT')
            cv = verifications[claim.verification]
            artifact = statement.artifact()
            covered_record = records[cv.evidence]
            if (cv.purpose != VerificationPurpose.COVERAGE or artifact not in cv.supporting_refs
                    or cv.scope_description != artifact or covered_record.source.artifact_ref != artifact
                    or covered_record.kind != EvidenceKind.SOURCE_OBSERVATION):
                raise AssessmentIntegrityError('COVERAGE_ASSERTION_NOT_VERIFIED')
            if covered_record.source.system != statement.source_system:
                block('coverage_source_system_mismatch', ReasonCode.MISSING_PROVENANCE)
            supporting_source = [v.reference() for v in verifications.values()
                if v.evidence == cv.evidence and v.purpose == VerificationPurpose.SOURCE
                and v.scope_description == 'scope:'+integrity_digest(request.scope)]
            if not supporting_source:
                block('coverage_source_not_verified', ReasonCode.UNVERIFIED_EVIDENCE)
            source_refs.extend(supporting_source)
            coverage_records.add(cv.evidence)
            if covered_record.quantity.state != ValueState.UNKNOWN:
                block('coverage_record_carries_unclassified_quantity', ReasonCode.MISSING_PROVENANCE)
            coverage_refs.append(cv.reference())
            if statement.representation == Representation.NOT_APPLICABLE:
                block('not_applicable_rule_unapproved', ReasonCode.MISSING_EVIDENCE)
                continue
            events = statement.evidence
            if len(set(events)) != len(events):
                block('duplicate_evidence_reference', ReasonCode.MISSING_PROVENANCE)
            if role in COUNTS and (len(events) != 1 or statement.representation != Representation.EVENTS):
                block('missing_or_competing_count', ReasonCode.MISSING_COUNT)
                continue
            if statement.representation == Representation.NO_MOVEMENTS:
                if events or role in COUNTS:
                    block('contradictory_no_movement_statement', ReasonCode.CONTRADICTORY_VARIANCE)
                else:
                    quantities[role] = Decimal('0')  # Derived from an independently verified closed coverage claim.
                continue
            if not events:
                block('empty_stream_without_no_movement_statement', ReasonCode.MISSING_MOVEMENT_COVERAGE)
                continue
            if statement.representation == Representation.AGGREGATE and len(events) != 1:
                block('overlapping_aggregate_and_events', ReasonCode.MISSING_MOVEMENT_COVERAGE)
            values = []
            for ref in events:
                if ref not in records:
                    raise AssessmentIntegrityError('MANIFEST_EVIDENCE_NOT_BOUND_TO_SNAPSHOT')
                r = records[ref]
                if ref in used:
                    block('overlapping_dependency_inputs', ReasonCode.MISSING_PROVENANCE)
                used.add(ref)
                identity = (r.source.system, r.source.record_id)
                if r.source.record_id is None or identity in seen_sources:
                    block('missing_or_duplicate_source_event', ReasonCode.MISSING_PROVENANCE)
                seen_sources.add(identity)
                if r.source.system != statement.source_system or r.kind != role:
                    block('source_or_role_mismatch', ReasonCode.MISSING_PROVENANCE)
                boundary = request.scope.period_start if role == EvidenceKind.OPENING_COUNT else request.scope.period_end
                valid_time = (r.effective_at == boundary if role in COUNTS else
                              r.effective_at is not None and request.scope.period_start <= r.effective_at < request.scope.period_end)
                if not valid_time:
                    block('observation_outside_role_period', ReasonCode.UNKNOWN_OBSERVATION_TIME)
                if r.quantity.state != ValueState.OBSERVED:
                    block('unknown_or_not_applicable_quantity', ReasonCode.MISSING_QUANTITY)
                else:
                    values.append(r.quantity.value)
                required = (VerificationPurpose.SOURCE, VerificationPurpose.COUNT) if role in COUNTS else (VerificationPurpose.SOURCE,)
                for purpose in required:
                    found = [v.reference() for v in verifications.values() if v.evidence == ref and v.purpose == purpose
                             and v.scope_description == 'scope:'+integrity_digest(request.scope)]
                    if not found:
                        block('unverified_'+purpose.value, ReasonCode.UNVERIFIED_EVIDENCE)
                    (source_refs if purpose == VerificationPurpose.SOURCE else count_refs).extend(found)
            if len(values) == len(events):
                with exact_arithmetic(values):
                    quantities[role] = sum(values, Decimal('0'))
        unexplained = {r.reference for r in snap.records if r.kind not in
                       (EvidenceKind.SOURCE_OBSERVATION, EvidenceKind.LEGACY_CLAIM)} - used
        if unexplained:
            block('unassigned_or_competing_inventory_records', ReasonCode.MISSING_MOVEMENT_COVERAGE)
        if {r.reference for r in snap.records if r.kind == EvidenceKind.SOURCE_OBSERVATION} - coverage_records:
            block('unassigned_source_observation', ReasonCode.MISSING_PROVENANCE)
    request_digest = integrity_digest({'request': request, 'profile_available': profile is not None,
                                      'manifest_available': manifest is not None, 'actor': ctx['actor']})
    previous = storage.previous(transaction, key, request_digest)
    now = TypeAdapter(Timestamp).validate_python(datetime.fromisoformat(ctx['now']))
    evaluated = (profile.evaluation_as_of if profile is not None and profile.evaluation_as_of is not None
                 else previous.provenance.evaluated_at if previous is not None else now)
    if evaluated > now:
        raise AssessmentIntegrityError('FUTURE_EVALUATION_CONTEXT')
    if any(r.ingested_at > evaluated for r in snap.records) or snap.created_at > evaluated:
        block('evaluation_precedes_snapshot', ReasonCode.UNKNOWN_OBSERVATION_TIME)
    if any(v.verified_at > evaluated for v in verifications.values()):
        block('evaluation_precedes_verification', ReasonCode.UNKNOWN_OBSERVATION_TIME)
    result = None
    domain: DomainReliabilityResult | None = None
    # Missing physical count is the only missing numeric accepted by the domain function.
    non_closing = set(ROLES)-{EvidenceKind.PHYSICAL_COUNT}
    closing_only_missing = (non_closing <= set(quantities) and EvidenceKind.PHYSICAL_COUNT not in quantities
                            and bool(details) and all(code == 'missing_physical_count' for code, _ in details))
    if not details or closing_only_missing:
        with exact_arithmetic(quantities.values()):
            inventory = InventoryRecord(restaurant_id=request.scope.restaurant_id,
                item_id=request.scope.item_id, item_name=request.scope.item_id, unit=request.scope.unit,
                period_start=request.scope.period_start, period_end=request.scope.period_end,
                **{field: quantities.get(role) for role, field in FIELDS.items()})
            result = reconcile_inventory(inventory)
            domain = assess_reliability(result, source_verified=True, count_verified=bool(count_refs),
                                         evidence_current=False)  # No approved freshness policy exists.
    # Operational blocking is separate from calculated reliability/confidence.
    block('production_authorization_policy_unavailable', ReasonCode.POLICY_UNAVAILABLE)
    if result is not None:
        if result.reliability_state == ReliabilityState.REVIEW_REQUIRED:
            block('nonzero_unexplained_variance', ReasonCode.REVIEW_REQUIRED)
        elif result.reliability_state == ReliabilityState.UNRELIABLE:
            block('negative_expected_inventory', ReasonCode.INVALID_QUANTITY)
    reasons = tuple(sorted({reason for _, reason in details}, key=lambda r:r.value))
    actions = {VerificationAction.DEFINE_POLICY}
    if any(r in reasons for r in (ReasonCode.MISSING_COUNT, ReasonCode.REVIEW_REQUIRED)):
        actions.add(VerificationAction.RECOUNT)
    if len(reasons)>1:
        actions.add(VerificationAction.PROVIDE_EVIDENCE)
    checks = (
        EvidenceCheck(kind=CheckKind.POLICY_AVAILABLE, status=CheckStatus.UNKNOWN,
                      reasons=(ReasonCode.POLICY_UNAVAILABLE,)),
        EvidenceCheck(kind=CheckKind.EVIDENCE_CURRENT, status=CheckStatus.UNKNOWN,
                      reasons=(ReasonCode.POLICY_UNAVAILABLE,)),
    )
    # No PASSED verification checks are emitted unless every mandatory input was validated.
    if result is not None and domain is not None and not closing_only_missing:
        checks += tuple(EvidenceCheck(kind=kind, status=CheckStatus.PASSED, verification_refs=tuple(sorted(set(refs),key=lambda r:str(r.verification_id))))
            for kind, refs in ((CheckKind.SOURCE_VERIFIED, source_refs), (CheckKind.COUNT_VERIFIED, count_refs),
                               (CheckKind.COVERAGE_COMPLETE, coverage_refs)) if refs)
    assessment = AssessmentEnvelope(schema_version='1.0.0', assessment_id=previous.assessment.assessment_id if previous is not None else uuid4(), assessor_id=ctx['actor'],
        scope=request.scope, domain=EvidenceDomain.INVENTORY, snapshots=(request.snapshot,),
        policy=VersionReference(identifier=request.profile.identifier, version=request.profile.version),
        assessed_at=evaluated, state=result.reliability_state if result is not None else ReliabilityState.INCOMPLETE,
        confidence=domain.evidence_confidence if domain is not None else EvidenceConfidence.UNKNOWN,
        decision_eligible=False, verification_required=True, checks=checks, reasons=reasons,
        required_actions=tuple(sorted(actions,key=lambda a:a.value)),
        expected_inventory=result.expected_inventory if result else None,
        actual_inventory=result.actual_inventory if result else None,
        unexplained_variance=result.unexplained_variance if result else None)
    provenance = CalculationProvenance(schema_version='1.0.0', request=request, evaluated_at=evaluated,
        profile_available=profile is not None, evidence=tuple(sorted(records,key=lambda r:str(r.evidence_id))),
        verifications=tuple(sorted(verifications,key=lambda r:str(r.verification_id))),
        details=tuple(BlockDetail(code=code,reason=reason) for code,reason in sorted(details)),
        assessment_digest=integrity_digest(calculation_body(assessment)))
    receipt = TrustedAssessmentReceipt(schema_version='1.0.0', assessment=assessment, provenance=provenance)
    if previous is not None:
        if previous != receipt:
            raise AssessmentIntegrityError('REPLAY_CALCULATION_MISMATCH')
        return previous
    return storage.save(transaction, key, request_digest, receipt)
