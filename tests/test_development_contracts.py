"""Boundary and consistency checks for the preserved remote development.

Failures here identify implementation gaps; they must not be skipped or have
expectations weakened just to obtain a green integration run.
"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.data_reliability.models import InventoryRecord, ReconciliationResult, ReliabilityState
from app.data_reliability.reconciliation import reconcile_inventory
from app.data_reliability.reliability import assess_reliability, EvidenceConfidence
from app.economic_engine.engine import EconomicEngine
from app.economic_engine.models import EconomicDecision, DecisionStatus, DecisionType
from app.economic_engine.measurement import EconomicMeasurement
from app.economic_engine.verification import verify_outcome, VerificationStatus


def inventory_record(**overrides):
    start = datetime(2026, 1, 1)
    values = dict(restaurant_id=101, item_id='ingredient', item_name='Ingredient', unit='kg',
                  period_start=start, period_end=start + timedelta(days=1),
                  beginning_inventory=Decimal('10.10'), receipts=Decimal('2.20'),
                  theoretical_usage=Decimal('1.10'), recorded_waste=Decimal('0.20'),
                  transfers_in=Decimal('0.30'), transfers_out=Decimal('0.10'),
                  adjustments=Decimal('-0.20'), physical_count=Decimal('11.00'))
    return InventoryRecord(**{**values, **overrides})


def test_decimal_reconciliation_and_evidence_gate():
    result = reconcile_inventory(inventory_record())
    assert result.expected_inventory == Decimal('11.00')
    assert result.unexplained_variance == Decimal('0.00')
    assert result.restaurant_id == 101 and result.unit == 'kg'
    unverified = assess_reliability(result)
    assert not unverified.decision_eligible and unverified.verification_required
    verified = assess_reliability(result, source_verified=True, count_verified=True, evidence_current=True)
    assert verified.decision_eligible and not verified.verification_required
    assert verified.evidence_confidence == EvidenceConfidence.HIGH


@pytest.mark.parametrize('field,value,error', [
    ('receipts', 1.0, TypeError), ('receipts', Decimal('NaN'), ValueError),
    ('receipts', Decimal('Infinity'), ValueError), ('receipts', Decimal('-1'), ValueError),
    ('restaurant_id', 0, ValueError), ('item_id', '', ValueError), ('unit', '', ValueError),
    ('period_end', datetime(2026, 1, 1), ValueError),
])
def test_invalid_inventory_inputs_rejected(field, value, error):
    with pytest.raises(error):
        inventory_record(**{field: value})






@pytest.mark.parametrize('source,count,current,confidence,eligible', [
    (False, False, False, EvidenceConfidence.LOW, False),
    (True, False, True, EvidenceConfidence.LOW, False),
    (False, True, True, EvidenceConfidence.LOW, False),
    (True, True, False, EvidenceConfidence.MEDIUM, False),
    (True, True, True, EvidenceConfidence.HIGH, True),
])
def test_evidence_flags_are_independent(source, count, current, confidence, eligible):
    assessment = assess_reliability(reconcile_inventory(inventory_record()),
                                    source_verified=source, count_verified=count, evidence_current=current)
    assert assessment.evidence_confidence == confidence
    assert assessment.decision_eligible is eligible
    assert assessment.verification_required is (not eligible)


def measurement():
    return EconomicMeasurement(restaurant_id=101, decision_type=DecisionType.INVENTORY,
                               baseline_value=100, actual_value=110,
                               measured_at=datetime(2026, 1, 1), decision_id='test-decision')


@pytest.mark.parametrize('quality,status', [
    (0, VerificationStatus.WEAK), (0.5999, VerificationStatus.WEAK),
    (0.60, VerificationStatus.MODERATE), (0.7999, VerificationStatus.MODERATE),
    (0.80, VerificationStatus.STRONG), (1, VerificationStatus.STRONG),
])
def test_verification_confidence_boundaries(quality, status):
    result = verify_outcome(measurement(), True, 1, quality)
    assert result.status == status
    assert result.confidence == quality
    assert result.observed_impact == 10 and result.decision_id == 'test-decision'


@pytest.mark.parametrize('compliance,quality', [(-0.1, 1), (1.1, 1), (1, -0.1), (1, 1.1), (float('nan'), 1)])
def test_invalid_confidence_is_rejected(compliance, quality):
    with pytest.raises(ValueError):
        verify_outcome(measurement(), True, compliance, quality)


def test_unexecuted_cycle_preserves_proposal_and_has_no_verified_learning():
    decision = EconomicDecision(restaurant_id=101, decision_type=DecisionType.INVENTORY,
                                description='Test proposal', recommended_value=10, unit='kg',
                                expected_economic_value=20, confidence=0.9, created_at=datetime(2026, 1, 1))
    result = EconomicEngine().complete_cycle(decision, 100, 110, False, 1, 1, 'unexecuted-test')
    assert result.decision.status == DecisionStatus.PROPOSED
    assert result.decision.actual_value is None and result.decision.executed_at is None
    assert result.verification.status == VerificationStatus.NOT_VERIFIED
    assert result.verification.confidence == 0
    assert not result.learning.verified
    assert result.learning.prediction_error == -10
    assert result.learning.decision_id == result.measurement.decision_id == 'unexecuted-test'
