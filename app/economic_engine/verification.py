from dataclasses import dataclass
from enum import Enum

from app.economic_engine.measurement import EconomicMeasurement


class VerificationStatus(str, Enum):
    NOT_VERIFIED = "not_verified"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


@dataclass
class VerificationResult:
    decision_id: str
    observed_impact: float
    confidence: float
    status: VerificationStatus
    reason: str


def verify_outcome(
    measurement: EconomicMeasurement,
    decision_executed: bool,
    compliance: float,
    data_quality: float,
) -> VerificationResult:

    if not 0.0 <= compliance <= 1.0:
        raise ValueError("compliance must be between 0 and 1")

    if not 0.0 <= data_quality <= 1.0:
        raise ValueError("data_quality must be between 0 and 1")

    impact = measurement.economic_impact

    if not decision_executed:
        return VerificationResult(
            decision_id=measurement.decision_id,
            observed_impact=impact,
            confidence=0.0,
            status=VerificationStatus.NOT_VERIFIED,
            reason="Decision was not executed.",
        )

    confidence = compliance * data_quality

    if confidence >= 0.80:
        status = VerificationStatus.STRONG
    elif confidence >= 0.60:
        status = VerificationStatus.MODERATE
    else:
        status = VerificationStatus.WEAK

    return VerificationResult(
        decision_id=measurement.decision_id,
        observed_impact=impact,
        confidence=confidence,
        status=status,
        reason=(
            "Verification strength is based on execution, "
            "operator compliance, and measurement data quality."
        ),
    )
