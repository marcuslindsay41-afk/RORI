from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.data_reliability.models import (
    ReconciliationResult,
    ReliabilityState,
)


class EvidenceConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReliabilityAssessment:
    restaurant_id: int
    item_id: str
    reliability_state: ReliabilityState
    evidence_confidence: EvidenceConfidence
    decision_eligible: bool
    verification_required: bool
    reason: str


def assess_reliability(
    result: ReconciliationResult,
    *,
    source_verified: bool = False,
    count_verified: bool = False,
    evidence_current: bool = False,
) -> ReliabilityAssessment:
    """
    Assess whether reconciled inventory is suitable
    for downstream operational decisions.

    Reconciliation alone does not prove that the
    underlying inventory records are trustworthy.

    Verification flags must come from actual evidence,
    not assumptions.
    """

    if not isinstance(result, ReconciliationResult):
        raise TypeError(
            "result must be a ReconciliationResult"
        )

    state = result.reliability_state

    if state == ReliabilityState.INCOMPLETE:
        return ReliabilityAssessment(
            restaurant_id=result.restaurant_id,
            item_id=result.item_id,
            reliability_state=state,
            evidence_confidence=EvidenceConfidence.UNKNOWN,
            decision_eligible=False,
            verification_required=True,
            reason="Required inventory evidence is missing.",
        )

    if state == ReliabilityState.UNRELIABLE:
        return ReliabilityAssessment(
            restaurant_id=result.restaurant_id,
            item_id=result.item_id,
            reliability_state=state,
            evidence_confidence=EvidenceConfidence.LOW,
            decision_eligible=False,
            verification_required=True,
            reason="Inventory records contain an invalid state.",
        )

    if state == ReliabilityState.REVIEW_REQUIRED:
        return ReliabilityAssessment(
            restaurant_id=result.restaurant_id,
            item_id=result.item_id,
            reliability_state=state,
            evidence_confidence=EvidenceConfidence.LOW,
            decision_eligible=False,
            verification_required=True,
            reason="Unexplained inventory variance requires review.",
        )

    if state != ReliabilityState.RELIABLE:
        return ReliabilityAssessment(
            restaurant_id=result.restaurant_id,
            item_id=result.item_id,
            reliability_state=state,
            evidence_confidence=EvidenceConfidence.UNKNOWN,
            decision_eligible=False,
            verification_required=True,
            reason="Unrecognized reliability state.",
        )

    if (
        result.actual_inventory is None
        or result.unexplained_variance is None
        or result.unexplained_variance != 0
        or result.verification_required
    ):
        return ReliabilityAssessment(
            restaurant_id=result.restaurant_id,
            item_id=result.item_id,
            reliability_state=state,
            evidence_confidence=EvidenceConfidence.LOW,
            decision_eligible=False,
            verification_required=True,
            reason="Reconciliation evidence is inconsistent.",
        )

    if (
        source_verified
        and count_verified
        and evidence_current
    ):
        return ReliabilityAssessment(
            restaurant_id=result.restaurant_id,
            item_id=result.item_id,
            reliability_state=state,
            evidence_confidence=EvidenceConfidence.HIGH,
            decision_eligible=True,
            verification_required=False,
            reason="Inventory reconciles and evidence checks passed.",
        )

    if source_verified and count_verified:
        confidence = EvidenceConfidence.MEDIUM
        reason = "Evidence freshness has not been verified."
    else:
        confidence = EvidenceConfidence.LOW
        reason = "Inventory reconciles but independent evidence is insufficient."

    return ReliabilityAssessment(
        restaurant_id=result.restaurant_id,
        item_id=result.item_id,
        reliability_state=state,
        evidence_confidence=confidence,
        decision_eligible=False,
        verification_required=True,
        reason=reason,
    )
