from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from enum import Enum
from typing import Optional


class ReliabilityState(str, Enum):
    RELIABLE = "reliable"
    REVIEW_REQUIRED = "review_required"
    UNRELIABLE = "unreliable"
    INCOMPLETE = "incomplete"


@dataclass
class InventoryRecord:
    restaurant_id: int
    item_id: str
    item_name: str
    unit: str
    period_start: datetime
    period_end: datetime

    beginning_inventory: Decimal
    receipts: Decimal
    theoretical_usage: Decimal
    recorded_waste: Decimal
    transfers_in: Decimal
    transfers_out: Decimal
    adjustments: Decimal

    physical_count: Optional[Decimal] = None

    def __post_init__(self):
        if self.restaurant_id <= 0:
            raise ValueError("Invalid restaurant ID")

        if not self.item_id or not self.unit:
            raise ValueError("Item ID and unit are required")

        if self.period_end <= self.period_start:
            raise ValueError("Invalid inventory period")

        fields = [
            "beginning_inventory",
            "receipts",
            "theoretical_usage",
            "recorded_waste",
            "transfers_in",
            "transfers_out",
            "adjustments",
            "physical_count",
        ]

        for field in fields:
            value = getattr(self, field)

            if value is None:
                continue

            if not isinstance(value, Decimal):
                raise TypeError(
                    f"{field} must be a Decimal"
                )

            if not value.is_finite():
                raise ValueError(
                    f"{field} must be finite"
                )

            if field != "adjustments" and value < 0:
                raise ValueError(
                    f"{field} cannot be negative"
                )


@dataclass
class ReconciliationResult:
    restaurant_id: int
    item_id: str
    unit: str

    expected_inventory: Decimal
    actual_inventory: Optional[Decimal]
    unexplained_variance: Optional[Decimal]

    reliability_state: ReliabilityState
    verification_required: bool
    reason: str
