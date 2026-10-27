from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.evidence_contracts.common import (ReasonCode, VerificationAction, Scope,
    VersionReference, SnapshotReference)
from app.evidence_contracts.decisions import (ReliabilityAssessment, DecisionEligibility,
    EligibilityOutcome, DecisionOperation, EvidenceCheck, CheckKind, CheckStatus)
from app.evidence_contracts.evidence import EvidenceDomain
from app.data_reliability.models import ReliabilityState
from app.data_reliability.reliability import EvidenceConfidence
from .factories import (NOW, eligible_assessment_data, denial_data, snapshot,
                        verification, record, POLICY)


def test_valid_inventory_assessment_is_not_itself_authorization():
    assessment = ReliabilityAssessment(**eligible_assessment_data())
    assert assessment.decision_eligible and assessment.state == ReliabilityState.RELIABLE
    assert assessment.reference().snapshots == assessment.snapshots
    assert assessment.actual_inventory - assessment.expected_inventory == 0
    data = denial_data()
    data.update(outcome=EligibilityOutcome.ALLOW, snapshots=assessment.snapshots,
                assessments=(assessment.reference(),), valid_until=NOW+timedelta(hours=1),
                reasons=(), required_actions=())
    with pytest.raises(ValidationError, match='no operational policies'):
        DecisionEligibility(**data)


@pytest.mark.parametrize('state', [ReliabilityState.INCOMPLETE, ReliabilityState.REVIEW_REQUIRED, ReliabilityState.UNRELIABLE])
def test_nonreliable_states_cannot_claim_eligibility(state):
    data = eligible_assessment_data()
    with pytest.raises(ValidationError):
        ReliabilityAssessment(**{**data, 'state': state})
    blocked = ReliabilityAssessment(**{**data, 'state': state, 'decision_eligible': False,
        'verification_required': True, 'confidence': (EvidenceConfidence.UNKNOWN
        if state == ReliabilityState.INCOMPLETE else EvidenceConfidence.LOW),
        'reasons': (ReasonCode.REVIEW_REQUIRED,),
        'required_actions': (VerificationAction.REASSESS,)})
    assert not blocked.decision_eligible and blocked.verification_required


@pytest.mark.parametrize('field,value', [
    ('expected_inventory', None), ('actual_inventory', None), ('unexplained_variance', None),
    ('actual_inventory', Decimal('90')), ('unexplained_variance', Decimal('10')),
    ('expected_inventory', Decimal('-1')), ('actual_inventory', Decimal('NaN')),
    ('expected_inventory', 0), ('decision_eligible', 'true'), ('verification_required', 'false'),
])
def test_invalid_or_contradictory_inventory_assessment_rejected(field, value):
    with pytest.raises(ValidationError):
        ReliabilityAssessment(**{**eligible_assessment_data(), field: value})


@pytest.mark.parametrize('field,value', [('reasons', (ReasonCode.STALE_EVIDENCE,)),
    ('required_actions', (VerificationAction.RECOUNT,)), ('verification_required', True),
    ('confidence', EvidenceConfidence.MEDIUM), ('snapshots', ()), ('checks', ())])
def test_eligibility_cannot_omit_evidence_or_hide_blockers(field, value):
    with pytest.raises(ValidationError):
        ReliabilityAssessment(**{**eligible_assessment_data(), field: value})


def test_nonzero_variance_cannot_claim_zero_through_a_reliable_label():
    data = eligible_assessment_data()
    data.update(expected_inventory=Decimal('100'), actual_inventory=Decimal('90'), unexplained_variance=Decimal('0'))
    with pytest.raises(ValidationError, match='zero variance'):
        ReliabilityAssessment(**data)


def test_other_domains_are_not_implicitly_certified_by_dr01():
    with pytest.raises(ValidationError, match='only inventory'):
        ReliabilityAssessment(**{**eligible_assessment_data(), 'domain': EvidenceDomain.SALES})


def test_missing_physical_count_can_be_recorded_as_incomplete_not_eligible():
    data = eligible_assessment_data()
    assessment = ReliabilityAssessment(**{**data, 'actual_inventory': None, 'unexplained_variance': None,
        'state': ReliabilityState.INCOMPLETE, 'confidence': EvidenceConfidence.UNKNOWN,
        'decision_eligible': False, 'verification_required': True,
        'reasons': (ReasonCode.MISSING_COUNT,), 'required_actions': (VerificationAction.RECOUNT,)})
    assert assessment.actual_inventory is None and not assessment.decision_eligible


@pytest.mark.parametrize('kind', [CheckKind.SOURCE_VERIFIED, CheckKind.COUNT_VERIFIED, CheckKind.COVERAGE_COMPLETE])
def test_verification_checks_cannot_be_self_asserted_without_references(kind):
    with pytest.raises(ValidationError, match='separate verification references'):
        EvidenceCheck(kind=kind, status=CheckStatus.PASSED)


def test_verification_check_cannot_use_the_wrong_verification_purpose():
    with pytest.raises(ValidationError, match='purpose'):
        EvidenceCheck(kind=CheckKind.COUNT_VERIFIED, status=CheckStatus.PASSED,
                      verification_refs=(verification(record().reference),))


def test_not_applicable_check_requires_documented_rule_and_does_not_pass_mandatory_check():
    with pytest.raises(ValidationError, match='documented'):
        EvidenceCheck(kind=CheckKind.EVIDENCE_CURRENT, status=CheckStatus.NOT_APPLICABLE)
    data = eligible_assessment_data()
    check = EvidenceCheck(kind=CheckKind.EVIDENCE_CURRENT, status=CheckStatus.NOT_APPLICABLE, rule=POLICY)
    data['checks'] = tuple(c for c in data['checks'] if c.kind != check.kind) + (check,)
    with pytest.raises(ValidationError, match='every mandatory check'):
        ReliabilityAssessment(**data)


@pytest.mark.parametrize('status', [CheckStatus.FAILED, CheckStatus.UNKNOWN])
def test_unknown_or_failed_freshness_blocks_assessment(status):
    data = eligible_assessment_data()
    check = EvidenceCheck(kind=CheckKind.EVIDENCE_CURRENT, status=status,
                          reasons=(ReasonCode.STALE_EVIDENCE,))
    data['checks'] = tuple(c for c in data['checks'] if c.kind != check.kind) + (check,)
    with pytest.raises(ValidationError, match='every mandatory check'):
        ReliabilityAssessment(**data)


def test_cross_tenant_assessments_and_eligibility_are_rejected():
    data = eligible_assessment_data()
    with pytest.raises(ValidationError, match='cross-tenant'):
        ReliabilityAssessment(**{**data, 'scope': Scope(restaurant_id=202)})
    with pytest.raises(ValidationError, match='cross-tenant'):
        DecisionEligibility(**{**denial_data(), 'snapshots': (SnapshotReference(
            restaurant_id=202, snapshot_id=uuid4(), digest='a'*64),)})


@pytest.mark.parametrize('reason', [ReasonCode.MISSING_EVIDENCE, ReasonCode.UNKNOWN_POLICY_VERSION,
    ReasonCode.UNKNOWN_MANIFEST, ReasonCode.REVOKED_EVIDENCE, ReasonCode.REVISION_MISMATCH,
    ReasonCode.STALE_EVIDENCE, ReasonCode.ASSESSMENT_FAILED])
def test_denials_retain_specific_operation_and_structured_reason(reason):
    denial = DecisionEligibility(**{**denial_data(), 'operation': DecisionOperation.PUBLISH,
                                   'reasons': (reason,)})
    assert denial.outcome == EligibilityOutcome.DENY
    assert denial.operation == DecisionOperation.PUBLISH and denial.reasons == (reason,)
    with pytest.raises(ValidationError, match='frozen'):
        denial.operation = DecisionOperation.EXECUTE


def test_denials_cannot_omit_correction_or_revocation_invalidation():
    data = denial_data()
    for field, value in [('invalidation_conditions', (ReasonCode.REVOKED_EVIDENCE,)),
                         ('reasons', ()), ('required_actions', ())]:
        with pytest.raises(ValidationError):
            DecisionEligibility(**{**data, field: value})


def test_assessment_bindings_cannot_be_swapped_to_a_different_snapshot_or_policy():
    assessment = ReliabilityAssessment(**eligible_assessment_data())
    data = {**denial_data(), 'snapshots': assessment.snapshots, 'assessments': (assessment.reference(),)}
    assert DecisionEligibility(**data).assessments == (assessment.reference(),)
    for changes in [{'snapshots': (snapshot().reference(),)},
                    {'policy': VersionReference(identifier='other-policy', version='1.0.0')}]:
        with pytest.raises(ValidationError, match='exact snapshot bindings'):
            DecisionEligibility(**{**data, **changes})


def test_no_universal_freshness_or_validity_interval_is_invented():
    denial = DecisionEligibility(**denial_data())
    assert denial.valid_until is None
    with pytest.raises(ValidationError, match='valid_until'):
        DecisionEligibility(**{**denial_data(), 'valid_until': NOW})


@pytest.mark.parametrize('operation', list(DecisionOperation))
def test_no_operation_can_be_authorized_before_a_trusted_gateway_and_policy_exist(operation):
    with pytest.raises(ValidationError, match='authorization is blocked'):
        DecisionEligibility(**{**denial_data(), 'operation': operation, 'outcome': EligibilityOutcome.ALLOW})


def test_unknown_policy_and_manifest_cannot_become_an_allow_record():
    data = denial_data()
    data.update(policy=VersionReference(identifier='unknown-policy', version='999.0.0'),
                dependency_manifest=VersionReference(identifier='unknown-manifest', version='999.0.0'),
                reasons=(ReasonCode.UNKNOWN_POLICY_VERSION, ReasonCode.UNKNOWN_MANIFEST))
    assert DecisionEligibility(**data).outcome == EligibilityOutcome.DENY
    with pytest.raises(ValidationError, match='authorization is blocked'):
        DecisionEligibility(**{**data, 'outcome': EligibilityOutcome.ALLOW})


def test_an_empty_evidence_snapshot_never_authorizes_any_operation():
    from app.evidence_contracts.evidence import EvidenceSnapshot
    from .factories import snapshot_data
    empty = EvidenceSnapshot(**snapshot_data(()))
    data = {**denial_data(), 'snapshots': (empty.reference(),), 'reasons': (ReasonCode.MISSING_EVIDENCE,)}
    assert DecisionEligibility(**data).outcome == EligibilityOutcome.DENY
    with pytest.raises(ValidationError, match='authorization is blocked'):
        DecisionEligibility(**{**data, 'outcome': EligibilityOutcome.ALLOW})


@pytest.mark.parametrize('state', [ReliabilityState.INCOMPLETE, ReliabilityState.UNRELIABLE, ReliabilityState.REVIEW_REQUIRED])
def test_nonreliable_assessment_cannot_claim_high_evidence_confidence(state):
    data = eligible_assessment_data()
    data.update(state=state, decision_eligible=False, verification_required=True,
                reasons=(ReasonCode.REVIEW_REQUIRED,), required_actions=(VerificationAction.REASSESS,))
    with pytest.raises(ValidationError, match='confidence contradicts'):
        ReliabilityAssessment(**data)


def test_decimal_underflow_cannot_disguise_a_nonzero_physical_discrepancy():
    data = eligible_assessment_data()
    data['actual_inventory'] = Decimal('1e-1000100')
    with pytest.raises(ValidationError, match='zero variance'):
        ReliabilityAssessment(**data)
