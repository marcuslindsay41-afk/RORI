"""Exact rational oracle, independent of the adapter's precision calculation."""
from datetime import timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from random import Random

import pytest

from app.inventory_assessment.arithmetic import exact_arithmetic
from app.inventory_assessment.errors import UnsupportedPrecision
from app.data_reliability.models import InventoryRecord
from app.data_reliability.reconciliation import reconcile_inventory
from tests.contracts.factories import NOW


def check_equation(values):
    opening, receipts, incoming, usage, waste, outgoing, adjustment, actual = values
    expected = (Fraction(opening)+Fraction(receipts)+Fraction(incoming)-Fraction(usage)
                -Fraction(waste)-Fraction(outgoing)+Fraction(adjustment))
    with exact_arithmetic(values):
        result = reconcile_inventory(InventoryRecord(restaurant_id=1, item_id='synthetic',
            item_name='synthetic', unit='kg', period_start=NOW, period_end=NOW+timedelta(days=1),
            beginning_inventory=opening, receipts=receipts, transfers_in=incoming,
            theoretical_usage=usage, recorded_waste=waste, transfers_out=outgoing,
            adjustments=adjustment, physical_count=actual))
    assert Fraction(result.expected_inventory) == expected
    if expected >= 0:
        assert Fraction(result.unexplained_variance) == Fraction(actual)-expected
    else:
        assert result.unexplained_variance is None


@pytest.mark.parametrize('ambient', [1, 3, 28, 100])
def test_seeded_inventory_equation_against_exact_rational_oracle(ambient):
    rng = Random(31032026)
    with localcontext() as context:
        context.prec = ambient
        for _ in range(500):
            # Decimal tuple construction does not round through ambient context.
            values = [Decimal((0, tuple(map(int, str(rng.randrange(10**40)))), rng.randrange(-80, 81)))
                      for _ in range(8)]
            values[6] = values[6].copy_negate() if rng.randrange(2) else values[6]
            check_equation(values)


@pytest.mark.parametrize('values', [
    ('1e2000', '1e-1000', '1e2000', '1e2000', '1e-1000', '1e2000', '-1e-1000', '0'),
    ('9'*2000,)*6 + ('-'+'9'*2000, '9'*2000),
    ('1e-4000',)*8,
    ('1e4090', '1e4090', '1e4090', '1e4090', '1e4090', '1e4090', '-1e4090', '1e4090'),
    ('0',)*8,
])
def test_extreme_alignment_cancellation_and_signed_adjustments(values):
    check_equation(tuple(map(Decimal, values)))


def test_precision_boundary_and_explicit_rejection():
    # Eight inputs reserve four carry digits; a 4092-column span is supported.
    check_equation(tuple(map(Decimal, ('1e4091', '0', '0', '0', '0', '0', '0', '0'))))
    for values in [('1e4092', '0'), ('1e4097',), ('1e3000', '1e-3000'), ('Infinity',)]:
        with pytest.raises(UnsupportedPrecision):
            with exact_arithmetic(tuple(map(Decimal, values))):
                pytest.fail('unsupported arithmetic accepted')


def test_many_event_additions_preserve_carry_headroom():
    values = (Decimal('99999999999999999999.99999999999999999999'),)*10001
    oracle = sum(map(Fraction, values), Fraction())
    with exact_arithmetic(values):
        total = sum(values, Decimal('0'))
    assert Fraction(total) == oracle
