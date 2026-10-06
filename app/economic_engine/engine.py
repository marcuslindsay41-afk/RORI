from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.economic_engine.models import (
   EconomicDecision,
   DecisionStatus,
)
from app.economic_engine.measurement import EconomicMeasurement
from app.economic_engine.verification import (
   VerificationResult,
   verify_outcome,
)
from app.economic_engine.learning import (
   EconomicLearning,
   create_learning,
)


@dataclass
class EconomicCycleResult:
   """
   Result of one completed Rori economic decision cycle.
   """

   decision: EconomicDecision
   measurement: EconomicMeasurement
   verification: VerificationResult
   learning: EconomicLearning


class EconomicEngine:
   """
   Coordinates Rori's economic decision lifecycle.

   Decision
       -> Execution
       -> Measurement
       -> Verification
       -> Economic Learning
   """

   def complete_cycle(
       self,
       decision: EconomicDecision,
       baseline_value: float,
       actual_value: float,
       executed: bool,
       operator_compliance: float,
       measurement_quality: float,
       decision_id: Optional[str] = None,
   ) -> EconomicCycleResult:

       if decision_id is None:
           decision_id = (
               f"{decision.restaurant_id}-"
               f"{decision.decision_type.value}-"
               f"{int(decision.created_at.timestamp())}"
           )

       measurement = EconomicMeasurement(
           restaurant_id=decision.restaurant_id,
           decision_type=decision.decision_type,
           baseline_value=baseline_value,
           actual_value=actual_value,
           measured_at=datetime.now(),
           decision_id=decision_id,
       )

       verification = verify_outcome(
           measurement,
           executed,
           operator_compliance,
           measurement_quality,
       )

       learning = create_learning(
           restaurant_id=decision.restaurant_id,
           decision_id=decision_id,
           decision_type=decision.decision_type,
           expected_impact=decision.expected_economic_value,
           verification=verification,
       )

       if executed:
           decision.actual_value = actual_value
           decision.executed_at = datetime.now()
           decision.status = DecisionStatus.VERIFIED

       return EconomicCycleResult(
           decision=decision,
           measurement=measurement,
           verification=verification,
           learning=learning,
       )