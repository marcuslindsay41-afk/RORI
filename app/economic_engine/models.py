from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class DecisionType(str, Enum):
    PREP = "prep"
    PURCHASING = "purchasing"
    LABOR = "labor"
    LOCATION = "location"
    INVENTORY = "inventory"
    MENU = "menu"
    OTHER = "other"


class DecisionStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    MODIFIED = "modified"
    REJECTED = "rejected"
    EXECUTED = "executed"
    VERIFIED = "verified"


@dataclass
class EconomicDecision:
    restaurant_id: int
    decision_type: DecisionType
    description: str
    recommended_value: float
    unit: str
    expected_economic_value: float
    confidence: float
    created_at: datetime

    actual_value: Optional[float] = None
    status: DecisionStatus = DecisionStatus.PROPOSED
    executed_at: Optional[datetime] = None


@dataclass
class EconomicOutcome:
    restaurant_id: int
    decision_type: DecisionType
    measured_at: datetime

    baseline_value: float
    actual_value: float
    economic_impact: float

    decision_id: Optional[str] = None