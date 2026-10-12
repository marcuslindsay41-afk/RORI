import unittest
from decimal import Decimal

from app.data_reliability.models import (
    ReconciliationResult,
    ReliabilityState,
)
from app.data_reliability.reliability import (
    assess_reliability,
    EvidenceConfidence,
)


class TestReliabilityAssessment(unittest.TestCase):

    def make_result(
        self,
        state=ReliabilityState.RELIABLE,
        actual=Decimal("100"),
        variance=Decimal("0"),
        verification_required=False,
    ):
        return ReconciliationResult(
            restaurant_id=1,
            item_id="chicken",
            unit="lb",
            expected_inventory=Decimal("100"),
            actual_inventory=actual,
            unexplained_variance=variance,
            reliability_state=state,
            verification_required=verification_required,
            reason="Test reconciliation result.",
        )

    def test_missing_inventory_count(self):
        result = self.make_result(
            state=ReliabilityState.INCOMPLETE,
            actual=None,
            variance=None,
            verification_required=True,
        )

        assessment = assess_reliability(result)

        self.assertFalse(assessment.decision_eligible)
        self.assertTrue(assessment.verification_required)
        self.assertEqual(
            assessment.evidence_confidence,
            EvidenceConfidence.UNKNOWN,
        )

    def test_invalid_inventory_state(self):
        result = self.make_result(
            state=ReliabilityState.UNRELIABLE,
            variance=None,
            verification_required=True,
        )

        assessment = assess_reliability(result)

        self.assertFalse(assessment.decision_eligible)
        self.assertEqual(
            assessment.evidence_confidence,
            EvidenceConfidence.LOW,
        )

    def test_unexplained_variance(self):
        result = self.make_result(
            state=ReliabilityState.REVIEW_REQUIRED,
            actual=Decimal("90"),
            variance=Decimal("-10"),
            verification_required=True,
        )

        assessment = assess_reliability(result)

        self.assertFalse(assessment.decision_eligible)
        self.assertTrue(assessment.verification_required)

    def test_unverified_reconciliation(self):
        result = self.make_result()

        assessment = assess_reliability(result)

        self.assertFalse(assessment.decision_eligible)
        self.assertEqual(
            assessment.evidence_confidence,
            EvidenceConfidence.LOW,
        )

    def test_verified_but_stale_evidence(self):
        result = self.make_result()

        assessment = assess_reliability(
            result,
            source_verified=True,
            count_verified=True,
            evidence_current=False,
        )

        self.assertFalse(assessment.decision_eligible)
        self.assertEqual(
            assessment.evidence_confidence,
            EvidenceConfidence.MEDIUM,
        )

    def test_fully_verified_evidence(self):
        result = self.make_result()

        assessment = assess_reliability(
            result,
            source_verified=True,
            count_verified=True,
            evidence_current=True,
        )

        self.assertTrue(assessment.decision_eligible)
        self.assertFalse(assessment.verification_required)
        self.assertEqual(
            assessment.evidence_confidence,
            EvidenceConfidence.HIGH,
        )


if __name__ == "__main__":
    unittest.main()