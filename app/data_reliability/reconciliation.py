from decimal import Decimal

from app.data_reliability.models import (
    InventoryRecord,
    ReconciliationResult,
    ReliabilityState,
)


def reconcile_inventory(
    record: InventoryRecord,
) -> ReconciliationResult:
    """
    Reconcile expected inventory against a physical count.

    Assumptions:
    - All quantities use the same normalized unit.
    - Theoretical usage excludes recorded waste.
    - Adjustments may be positive or negative.
    """

    expected = (
        record.beginning_inventory
        + record.receipts
        + record.transfers_in
        - record.theoretical_usage
        - record.recorded_waste
        - record.transfers_out
        + record.adjustments
    )

    if expected < Decimal("0"):
        return ReconciliationResult(
            restaurant_id=record.restaurant_id,
            item_id=record.item_id,
            unit=record.unit,
            expected_inventory=expected,
            actual_inventory=record.physical_count,
            unexplained_variance=None,
            reliability_state=ReliabilityState.UNRELIABLE,
            verification_required=True,
            reason="Expected inventory is negative; review movement records.",
        )

    if record.physical_count is None:
        return ReconciliationResult(
            restaurant_id=record.restaurant_id,
            item_id=record.item_id,
            unit=record.unit,
            expected_inventory=expected,
            actual_inventory=None,
            unexplained_variance=None,
            reliability_state=ReliabilityState.INCOMPLETE,
            verification_required=True,
            reason="Physical inventory count is missing.",
        )

    variance = record.physical_count - expected

    if variance == Decimal("0"):
        state = ReliabilityState.RELIABLE
        required = False
        reason = "Inventory reconciles exactly."
    else:
        state = ReliabilityState.REVIEW_REQUIRED
        required = True
        reason = "Unexplained inventory variance requires review."

    return ReconciliationResult(
        restaurant_id=record.restaurant_id,
        item_id=record.item_id,
        unit=record.unit,
        expected_inventory=expected,
        actual_inventory=record.physical_count,
        unexplained_variance=variance,
        reliability_state=state,
        verification_required=required,
        reason=reason,
    )
