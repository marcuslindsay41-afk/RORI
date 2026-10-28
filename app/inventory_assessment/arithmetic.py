"""Exact Decimal execution v1. Resource limits are not economic thresholds."""
from contextlib import contextmanager
from decimal import (Context, Decimal, localcontext, Inexact, Rounded, InvalidOperation,
                     Overflow, Underflow, Clamped, FloatOperation, DecimalException, ROUND_HALF_EVEN, DivisionByZero)
from .errors import UnsupportedPrecision

ARITHMETIC_VERSION = 'exact-decimal-1.0.0'
MAX_PRECISION = 4096
MAX_EXPONENT = 4096


@contextmanager
def exact_arithmetic(values):
    values = tuple(values)
    if any(not isinstance(v, Decimal) or not v.is_finite() for v in values):
        raise UnsupportedPrecision('INVALID_DECIMAL')
    if any(len(v.as_tuple().digits) > MAX_PRECISION or abs(v.as_tuple().exponent) > MAX_EXPONENT
           or abs(v.adjusted()) > MAX_EXPONENT for v in values):
        raise UnsupportedPrecision('UNSUPPORTED_PRECISION')
    nonzero = tuple(v for v in values if v)
    span = (max(v.adjusted() for v in nonzero) - min([v.as_tuple().exponent for v in values] + [0]) + 1
            if nonzero else 1)
    precision = max(span, max((len(v.as_tuple().digits) for v in values), default=1)) + len(str(len(values)+8)) + 2
    if precision > MAX_PRECISION:
        raise UnsupportedPrecision('UNSUPPORTED_PRECISION')
    context = Context(prec=precision, Emin=-999999, Emax=999999, rounding=ROUND_HALF_EVEN,
                      capitals=1, clamp=0, flags=[], traps=[])
    for signal in (Inexact, Rounded, InvalidOperation, Overflow, Underflow, Clamped, FloatOperation, DivisionByZero):
        context.traps[signal] = True
    try:
        with localcontext(context):
            yield
    except DecimalException as exc:
        raise UnsupportedPrecision('EXACT_ARITHMETIC_NOT_REPRESENTABLE') from exc
