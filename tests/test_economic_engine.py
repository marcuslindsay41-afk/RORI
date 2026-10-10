import unittest
from datetime import datetime

from app.economic_engine.engine import EconomicEngine
from app.economic_engine.models import EconomicDecision, DecisionType


class TestEconomicEngine(unittest.TestCase):

    def setUp(self):
        self.engine = EconomicEngine()

    def make_decision(self):
        return EconomicDecision(
            restaurant_id=1,
            decision_type=DecisionType.PREP,
            description="Prep chicken",
            recommended_value=64,
            unit="units",
            expected_economic_value=143.0,
            confidence=0.82,
            created_at=datetime.now(),
        )

    def test_successful_economic_cycle(self):
        decision = self.make_decision()

        result = self.engine.complete_cycle(
            decision,
            1000.0,
            1140.0,
            True,
            0.90,
            0.95,
            "test-cycle-001",
        )

        self.assertEqual(
            result.measurement.economic_impact,
            140.0,
        )

        self.assertEqual(
            result.verification.status.value,
            "strong",
        )

        self.assertAlmostEqual(
            result.verification.confidence,
            0.855,
        )

        self.assertEqual(
            result.learning.prediction_error,
            -3.0,
        )

        self.assertAlmostEqual(
            result.learning.accuracy_ratio,
            140.0 / 143.0,
        )

        self.assertTrue(result.learning.verified)

        self.assertEqual(
            result.decision.status.value,
            "verified",
        )

    def test_decision_not_executed(self):
        decision = self.make_decision()

        result = self.engine.complete_cycle(
            decision,
            1000.0,
            1140.0,
            False,
            0.90,
            0.95,
            "test-cycle-002",
        )

        self.assertNotEqual(
            result.verification.status.value,
            "strong",
        )

        self.assertFalse(
            result.learning.verified,
        )


if __name__ == "__main__":
    unittest.main()
