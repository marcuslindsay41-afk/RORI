from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .models import DecisionType


@dataclass
class EconomicMeasurement:
    restaurant_id: int
    decision_type: DecisionType

    baseline_value: float
    actual_value: float
    measured_at: datetime

    decision_id: Optional[str] = None

    @property
    def economic_impact(self) -> float:
        """
        Raw observed difference between actual and baseline.

        Positive = improvement relative to baseline.
        Negative = deterioration relative to baseline.

        This is measurement, NOT causal attribution.
        """
        return self.actual_value - self.baseline_value