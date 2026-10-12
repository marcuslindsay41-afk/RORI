import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from app.data_reliability.models import (
    InventoryRecord,
    ReliabilityState,
)
from app.data_reliability.reconciliation import reconcile_inventory


class TestInventoryReconciliation(unittest.TestCase):

    def make_record(self, **overrides):
        start = datetime(2026, 10, 1)

        data = {
            "restaurant_id": 1,
            "item_id": "CHICKEN-001",
            "item_name": "Chicken",
            "unit": "lb",
            "period_start": start,
            "period_end": start + timedelta(days=1),
            "beginning_inventory": Decimal("100"),
            "receipts": Decimal("50"),
            "theoretical_usage": Decimal("60"),
            "recorded_waste": Decimal("5"),
            "transfers_in": Decimal("10"),
            "transfers_out": Decimal("5"),
            "adjustments": Decimal("0"),
            "physical_count": Decimal("90"),
        }

        data.update(overrides)
        return InventoryRecord(**data)

    def test_accurate_inventory(self):
        record = self.make_record()
        result = reconcile_inventory(record)

        self.assertEqual(
            result.expected_inventory,
            Decimal("90"),
        )
        self.assertEqual(
            result.actual_inventory,
            Decimal("90"),
        )
        self.assertEqual(
            result.unexplained_variance,
            Decimal("0"),
        )
        self.assertEqual(
            result.reliability_state,
            ReliabilityState.RELIABLE,
        )
        self.assertFalse(result.verification_required)

    def test_inventory_shortage(self):
        record = self.make_record(
            physical_count=Decimal("80")
        )
        result = reconcile_inventory(record)

        self.assertEqual(
            result.unexplained_variance,
            Decimal("-10"),
        )
        self.assertEqual(
            result.reliability_state,
            ReliabilityState.REVIEW_REQUIRED,
        )
        self.assertTrue(result.verification_required)

    def test_inventory_surplus(self):
        record = self.make_record(
            physical_count=Decimal("100")
        )
        result = reconcile_inventory(record)

        self.assertEqual(
            result.unexplained_variance,
            Decimal("10"),
        )
        self.assertEqual(
            result.reliability_state,
            ReliabilityState.REVIEW_REQUIRED,
        )
        self.assertTrue(result.verification_required)

    def test_missing_physical_count(self):
        record = self.make_record(
            physical_count=None
        )
        result = reconcile_inventory(record)

        self.assertEqual(
            result.expected_inventory,
            Decimal("90"),
        )
        self.assertIsNone(result.actual_inventory)
        self.assertIsNone(result.unexplained_variance)
        self.assertEqual(
            result.reliability_state,
            ReliabilityState.INCOMPLETE,
        )
        self.assertTrue(result.verification_required)

    def test_negative_expected_inventory(self):
        record = self.make_record(
            theoretical_usage=Decimal("200")
        )
        result = reconcile_inventory(record)

        self.assertEqual(
            result.expected_inventory,
            Decimal("-50"),
        )
        self.assertIsNone(result.unexplained_variance)
        self.assertEqual(
            result.reliability_state,
            ReliabilityState.UNRELIABLE,
        )
        self.assertTrue(result.verification_required)

    def test_invalid_negative_input(self):
        with self.assertRaises(ValueError):
            self.make_record(
                receipts=Decimal("-10")
            )


if __name__ == "__main__":
    unittest.main()
