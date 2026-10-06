from dataclasses import dataclass
from datetime import datetime

from app.economic_engine.models import DecisionType
from app.economic_engine.verification import VerificationResult


@dataclass
class EconomicLearning:
    restaurant_id: int
    decision_id: str
    decision_type: DecisionType

    expected_impact: float
    observed_impact: float
    prediction_error: float

    verification_confidence: float
    verified: bool

    learned_at: datetime

    @property
    def absolute_error(self) -> float:
        return abs(self.prediction_error)

    @property
    def accuracy_ratio(self) -> float:
        if self.expected_impact == 0:
            return 0.0

        error_ratio = self.absolute_error / abs(self.expected_impact)
        return max(0.0, 1.0 - error_ratio)


def create_learning(
    restaurant_id: int,
    decision_id: str,
    decision_type: DecisionType,
    expected_impact: float,
    verification: VerificationResult,
) -> EconomicLearning:

    observed_impact = verification.observed_impact

    return EconomicLearning(
        restaurant_id=restaurant_id,
        decision_id=decision_id,
        decision_type=decision_type,
        expected_impact=expected_impact,
        observed_impact=observed_impact,
        prediction_error=observed_impact - expected_impact,
        verification_confidence=verification.confidence,
        verified=verification.status.value == "strong",
        learned_at=datetime.now(),
    )