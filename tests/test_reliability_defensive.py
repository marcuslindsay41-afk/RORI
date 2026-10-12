import unittest
from decimal import Decimal
from inspect import signature

from app.data_reliability.models import (
    ReconciliationResult,
    ReliabilityState,
)
from app.data_reliability.reliability import assess_reliability


class TestReliabilityDefensive(unittest.TestCase):

    def make_result(
        self,
        state=ReliabilityState.RELIABLE,
        variance=Decimal("0"),
        actual=Decimal("100"),
        verification_required=False,
    ):
        return ReconciliationResult(
            restaurant_id=1,
            item_id="TEST-001",
            unit="each",
            expected_inventory=Decimal("100"),
            actual_inventory=actual,
            unexplained_variance=variance,
            reliability_state=state,
            verification_required=verification_required,
            reason="Defensive test",
        )

    def assess(self, result, **evidence):
        parameters = signature(assess_reliability).parameters

        kwargs = {
            name: value
            for name, value in evidence.items()
            if name in parameters
        }

        return assess_reliability(result, **kwargs)

    def test_reliable_state_with_unexplained_variance(self):
        result = self.make_result(
            state=ReliabilityState.RELIABLE,
            variance=Decimal("10"),
        )

        assessment = self.assess(result)

        self.assertFalse(
            assessment.decision_eligible,
            "Contradictory inventory evidence must not be eligible.",
        )

    def test_reliable_state_with_missing_count(self):
        result = self.make_result(
            actual=None,
            variance=None,
        )

        assessment = self.assess(result)

        self.assertFalse(
            assessment.decision_eligible,
            "Missing physical counts must block eligibility.",
        )

    def test_unreliable_state_blocks_decision(self):
        result = self.make_result(
            state=ReliabilityState.UNRELIABLE,
            variance=Decimal("20"),
            verification_required=True,
        )

        assessment = self.assess(result)

        self.assertFalse(assessment.decision_eligible)

    def test_incomplete_state_blocks_decision(self):
        result = self.make_result(
            state=ReliabilityState.INCOMPLETE,
            actual=None,
            variance=None,
            verification_required=True,
        )

        assessment = self.assess(result)

        self.assertFalse(assessment.decision_eligible)

    def test_review_required_blocks_decision(self):
        result = self.make_result(
            state=ReliabilityState.REVIEW_REQUIRED,
            variance=Decimal("5"),
            verification_required=True,
        )

        assessment = self.assess(result)

        self.assertFalse(assessment.decision_eligible)


if __name__ == "__main__":
    unittest.main()
