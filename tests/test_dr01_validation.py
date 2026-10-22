"""Quantity validity and independently verified reconciliation evidence."""
from dataclasses import asdict
from decimal import Decimal

import pytest

from app.data_reliability.models import InventoryRecord, ReconciliationResult, ReliabilityState
from app.data_reliability.reconciliation import reconcile_inventory
from app.data_reliability.reliability import assess_reliability, EvidenceConfidence
from tests.test_development_contracts import inventory_record

REQUIRED = ('beginning_inventory', 'receipts', 'theoretical_usage', 'recorded_waste',
            'transfers_in', 'transfers_out', 'adjustments')


@pytest.mark.parametrize('field', REQUIRED)
@pytest.mark.parametrize('value', [None, '', '1.25', 'nonnumeric', 1, 1.25, True,
                                  Decimal('NaN'), Decimal('sNaN'),
                                  Decimal('Infinity'), Decimal('-Infinity')])
def test_required_quantities_reject_invalid_values(field, value):
    with pytest.raises((TypeError, ValueError), match=field):
        inventory_record(**{field: value})


@pytest.mark.parametrize('field', REQUIRED)
def test_omitted_required_quantity_is_rejected(field):
    values = asdict(inventory_record())
    del values[field]
    with pytest.raises(TypeError, match=field):
        InventoryRecord(**values)


@pytest.mark.parametrize('field', REQUIRED[:-1])
def test_unsigned_quantities_reject_negative_values(field):
    with pytest.raises(ValueError, match=field):
        inventory_record(**{field: Decimal('-0.01')})


@pytest.mark.parametrize('adjustment', [Decimal('-0.20'), Decimal('0'), Decimal('0.20')])
def test_signed_adjustments_and_zero_movements_remain_valid(adjustment):
    record = inventory_record(beginning_inventory=Decimal('10'), receipts=Decimal('0'),
                              theoretical_usage=Decimal('0'), recorded_waste=Decimal('0'),
                              transfers_in=Decimal('0'), transfers_out=Decimal('0'),
                              adjustments=adjustment, physical_count=Decimal('10') + adjustment)
    result = reconcile_inventory(record)
    assert result.expected_inventory == Decimal('10') + adjustment
    assert result.unexplained_variance == 0
    assert result.reliability_state == ReliabilityState.RELIABLE
    assert not result.verification_required


@pytest.mark.parametrize('value', ['', 1.25, Decimal('-1'), Decimal('NaN'), Decimal('Infinity')])
def test_present_physical_count_must_be_valid(value):
    with pytest.raises((TypeError, ValueError), match='physical_count'):
        inventory_record(physical_count=value)


def assessment_result(**overrides):
    values = dict(restaurant_id=101, item_id='ingredient', unit='kg',
                  expected_inventory=Decimal('100'), actual_inventory=Decimal('100'),
                  unexplained_variance=Decimal('0'), reliability_state=ReliabilityState.RELIABLE,
                  verification_required=False, reason='Test evidence')
    return ReconciliationResult(**{**values, **overrides})


def verified_assessment(result):
    return assess_reliability(result, source_verified=True, count_verified=True, evidence_current=True)


@pytest.mark.parametrize('actual,claimed', [
    (Decimal('90'), Decimal('0')), (Decimal('110'), Decimal('0')),
    (Decimal('100'), Decimal('10')), (Decimal('90'), Decimal('10')),
    (Decimal('90'), Decimal('-10')), (Decimal('110'), Decimal('10')),
])
def test_variance_is_recomputed_before_eligibility(actual, claimed):
    result = assessment_result(actual_inventory=actual, unexplained_variance=claimed)
    before = asdict(result)
    assessment = verified_assessment(result)
    assert not assessment.decision_eligible
    assert assessment.verification_required
    assert assessment.evidence_confidence == EvidenceConfidence.LOW
    assert asdict(result) == before


@pytest.mark.parametrize('field', ['expected_inventory', 'actual_inventory', 'unexplained_variance'])
@pytest.mark.parametrize('value', [None, '100', 100, Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity')])
def test_invalid_result_quantities_fail_closed(field, value):
    assessment = verified_assessment(assessment_result(**{field: value}))
    assert not assessment.decision_eligible
    assert assessment.verification_required
    assert assessment.evidence_confidence == EvidenceConfidence.LOW


@pytest.mark.parametrize('field', ['expected_inventory', 'actual_inventory'])
def test_negative_result_counts_fail_closed(field):
    assessment = verified_assessment(assessment_result(**{field: Decimal('-1')}))
    assert not assessment.decision_eligible
    assert assessment.verification_required


@pytest.mark.parametrize('state', list(ReliabilityState))
def test_only_reliable_consistent_state_can_be_eligible(state):
    assessment = verified_assessment(assessment_result(reliability_state=state))
    assert assessment.decision_eligible is (state == ReliabilityState.RELIABLE)
    assert assessment.verification_required is (state != ReliabilityState.RELIABLE)


def test_count_and_reliability_state_transitions():
    incomplete = reconcile_inventory(inventory_record(physical_count=None))
    assert incomplete.reliability_state == ReliabilityState.INCOMPLETE
    assert incomplete.actual_inventory is None and incomplete.unexplained_variance is None
    assert not verified_assessment(incomplete).decision_eligible

    shortage = reconcile_inventory(inventory_record(physical_count=Decimal('10')))
    assert shortage.unexplained_variance == Decimal('-1')
    assert shortage.reliability_state == ReliabilityState.REVIEW_REQUIRED
    assert not verified_assessment(shortage).decision_eligible

    reconciled = reconcile_inventory(inventory_record(physical_count=Decimal('11')))
    assert reconciled.reliability_state == ReliabilityState.RELIABLE
    assert reconciled.unexplained_variance == Decimal('0')
    assert not assess_reliability(reconciled).decision_eligible
    assert verified_assessment(reconciled).decision_eligible

    unreliable = reconcile_inventory(inventory_record(theoretical_usage=Decimal('100')))
    assert unreliable.expected_inventory < 0
    assert unreliable.reliability_state == ReliabilityState.UNRELIABLE
    assert unreliable.unexplained_variance is None
    assert not verified_assessment(unreliable).decision_eligible


def test_explicit_review_requirement_is_never_overridden():
    assessment = verified_assessment(assessment_result(verification_required=True))
    assert not assessment.decision_eligible
    assert assessment.verification_required
