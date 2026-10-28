from datetime import timedelta
from decimal import Decimal, localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.inventory_assessment.arithmetic import exact_arithmetic
from app.inventory_assessment.errors import UnsupportedPrecision
from app.inventory_assessment.contracts import (AssessmentProfile, ProfileStatus, ROLES,
    CoverageStatement, Representation, InventoryManifest, TrustedAssessmentReceipt,
    CalculationProvenance, AssessmentRequest, ProfileReference, calculation_body)
from app.evidence_contracts.common import integrity_digest, ReasonCode
from app.evidence_contracts.decisions import ReliabilityAssessment
from app.data_reliability.models import ReliabilityState
from app.data_reliability.reliability import EvidenceConfidence
from tests.contracts.factories import NOW, scope, snapshot, eligible_assessment_data, denial_data


def profile_data():
    return dict(schema_version='1.0.0',identifier='synthetic',version='1.0.0',
        status=ProfileStatus.SYNTHETIC_TEST_APPROVED,approval_reference='test-only',
        interval='movements_start_inclusive_end_exclusive_counts_at_boundaries',timezone='UTC',
        location_scope='restaurant_aggregate_only',unit='kg',unit_basis='native_canonical_no_conversion',
        usage_basis='excludes_recorded_waste',dependency_roles=ROLES,
        cardinality='one_stream_per_role_one_count_at_each_boundary',verification_issuers=('test-verifier',),
        verification_methods=('test-method',),source_systems=('test-source',),evaluation_as_of=NOW)


@pytest.mark.parametrize('precision',[1,3,28,100])
def test_exact_context_preserves_high_precision_and_restores_ambient_context(precision):
    a=Decimal('12345678901234567890.123456789012345678901')
    b=Decimal('0.000000000000000000001')
    with localcontext() as ambient:
        ambient.prec=precision
        with exact_arithmetic((a,b)):
            assert a+b==Decimal('12345678901234567890.123456789012345678902')
        assert ambient.prec==precision


@pytest.mark.parametrize('values',[(Decimal('1e-1000100'),),(Decimal('1e5000'),),
    (Decimal('1.'+'2'*4096),),(Decimal('1e4000'),Decimal('1e-4000')),
    (Decimal('NaN'),),(Decimal('Infinity'),),(0.1,), (None,)])
def test_unsupported_precision_and_invalid_values_fail_explicitly(values):
    with pytest.raises(UnsupportedPrecision):
        with exact_arithmetic(values):pytest.fail('unsupported arithmetic accepted')


def test_profile_is_exact_versioned_and_tamper_evident():
    profile=AssessmentProfile(**profile_data())
    assert AssessmentProfile.model_validate_json(profile.model_dump_json())==profile
    assert profile.reference().digest==profile.digest
    with pytest.raises(ValidationError,match='digest'):
        AssessmentProfile(**{**profile.model_dump(),'unit':'g'})


@pytest.mark.parametrize('field,value',[('version','2.0.0'),('arithmetic','ambient'),
    ('evaluation_as_of',None),('dependency_roles',()),('verification_methods',()),
    ('status','production_approved'),('timezone','local'),('usage_basis','includes_waste')])
def test_profile_cannot_invent_approval_semantics_or_omit_dependencies(field,value):
    with pytest.raises(ValidationError):AssessmentProfile(**{**profile_data(),field:value})


def receipt():
    data=eligible_assessment_data()
    data.update(decision_eligible=False,verification_required=True,checks=(),
        reasons=(ReasonCode.POLICY_UNAVAILABLE,), required_actions=denial_data()['required_actions'])
    assessment=ReliabilityAssessment(**data)
    request=AssessmentRequest(snapshot=assessment.snapshots[0],profile=ProfileReference(
        identifier=assessment.policy.identifier,version=assessment.policy.version,digest='0'*64),
        manifest_id=uuid4(),manifest_digest='1'*64,scope=assessment.scope)
    provenance=CalculationProvenance(schema_version='1.0.0',request=request,evaluated_at=NOW,
        profile_available=True,evidence=(),verifications=(),details=(),
        assessment_digest=integrity_digest(calculation_body(assessment)))
    return TrustedAssessmentReceipt(schema_version='1.0.0',assessment=assessment,provenance=provenance)


@pytest.mark.parametrize('changes',[
    {'expected_inventory':Decimal('1'),'actual_inventory':Decimal('5'),'unexplained_variance':Decimal('0')},
    {'state':ReliabilityState.REVIEW_REQUIRED,'confidence':EvidenceConfidence.LOW},
    {'actual_inventory':None}, {'unexplained_variance':Decimal('1')},
])
def test_blocked_receipt_rejects_contradictory_calculated_quantities(changes):
    previous=receipt()
    assessment=ReliabilityAssessment(**{**previous.assessment.model_dump(),**changes})
    prov=CalculationProvenance(**{**previous.provenance.model_dump(exclude={'computation_digest'}),
                                 'assessment_digest':integrity_digest(calculation_body(assessment))})
    with pytest.raises(ValidationError):
        TrustedAssessmentReceipt(schema_version='1.0.0',assessment=assessment,provenance=prov)


def test_receipt_digest_binds_calculation_even_when_operationally_blocked():
    value=receipt()
    assert TrustedAssessmentReceipt.model_validate_json(value.model_dump_json())==value
    with pytest.raises(ValidationError,match='digest'):
        CalculationProvenance(**{**value.provenance.model_dump(),'evaluated_at':NOW+timedelta(seconds=1)})


def test_decimal_traps_are_typed_and_never_silently_round():
    with pytest.raises(UnsupportedPrecision,match='NOT_REPRESENTABLE'):
        with exact_arithmetic((Decimal('1'),Decimal('3'))):
            Decimal('1')/Decimal('3')
    with pytest.raises(UnsupportedPrecision):
        with exact_arithmetic((Decimal('1e4096'),Decimal('0'))):
            pytest.fail('alignment beyond resource bound accepted')


def test_process_default_context_cannot_change_adapter_arithmetic():
    from decimal import DefaultContext, ROUND_FLOOR, Inexact
    original=DefaultContext.copy()
    try:
        DefaultContext.rounding=ROUND_FLOOR
        DefaultContext.prec=1
        DefaultContext.traps[Inexact]=False
        with exact_arithmetic((Decimal('12345'),Decimal('1'))):
            assert Decimal('12345')+Decimal('1')==Decimal('12346')
            with pytest.raises(Inexact):
                Decimal('1')/Decimal('3')
    finally:
        DefaultContext.rounding=original.rounding
        DefaultContext.prec=original.prec
        DefaultContext.traps=original.traps.copy()
