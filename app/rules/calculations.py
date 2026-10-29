"""Numerical legacy diagnostics, not recommendations or authorization.

Inputs are explicit finite observations supplied by the caller. No tenant/session,
database, source-resolution, instructions, priority, suggested actions, I/O or
verification/eligibility state is accepted or returned. Empty/unknown observations
do not become observed zero. Valid-input arithmetic preserves the legacy formulas.
"""
from math import isfinite

_WASTE_STOCK_TO_SALES_RATIO = 3.0


def _number(value):
    if type(value) not in (int, float):
        raise ValueError('An explicit finite nonnegative number is required')
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError('Unsupported numerical magnitude') from exc
    if not isfinite(result) or result < 0:
        raise ValueError('An explicit finite nonnegative number is required')
    return result


def inventory_metrics(stock: int, sold: int, cost: float):
    """Return carrying/excess exposure numbers, or None below the legacy thresholds."""
    if type(stock) is not int or type(sold) is not int or stock < 0 or sold < 0:
        raise ValueError('Explicit nonnegative integer quantities are required')
    cost = _number(cost)
    if sold == 0:
        if stock <= 20:
            return None
        return {'units_in_stock': stock, 'cost_per_unit_usd': round(cost, 2),
                'estimated_weekly_loss_usd': _number(round(stock * cost * 0.08, 2)),
                'overstock_pct': None}
    ratio = stock / sold
    if ratio < _WASTE_STOCK_TO_SALES_RATIO:
        return None
    excess_pct = int(round((stock - sold) / max(stock, 1) * 100))
    excess_pct = min(95, max(0, excess_pct))
    weekly_sold = sold / 2.0
    ideal_ceiling = max(sold, weekly_sold * 2)
    excess_units = max(0, int(stock - ideal_ceiling))
    return {'units_in_stock': stock, 'units_sold_period': sold,
            'stock_to_sales_ratio': round(ratio, 2), 'overstock_pct': excess_pct,
            'cost_per_unit_usd': round(cost, 2),
            'estimated_weekly_loss_usd': _number(round(excess_units * cost * 0.15, 2))}


def revenue_metrics(revenues: tuple):
    """Summarize supplied revenue observations; indices are positions, not item identities."""
    if type(revenues) is not tuple:
        raise ValueError('A concrete tuple of numerical observations is required')
    values = tuple(_number(v) for v in revenues)
    if not values:
        return {'bottom_items': (), 'avg_revenue_usd': None, 'items_in_menu': 0}
    total = _number(sum(values))
    avg_rev = total / len(values)
    bottom = sorted(range(len(values)), key=lambda i: values[i])[:3]
    items = []
    for index in bottom:
        rev = values[index]
        pct_below = round((avg_rev - rev) / avg_rev * 100, 0) if avg_rev > 0 else 0.0
        items.append({'index': index, 'revenue_usd': round(rev, 2),
                      'pct_below_period_avg': min(100.0, max(0.0, pct_below))})
    return {'bottom_items': tuple(items), 'avg_revenue_usd': round(avg_rev, 2),
            'items_in_menu': len(values)}


def labor_metrics(total_rev: float, total_labor: float):
    """Return supplied labor/revenue ratios and dollar differences; no staffing instruction."""
    total_rev, total_labor = _number(total_rev), _number(total_labor)
    threshold = 0.30
    cap_30 = round(total_rev * threshold, 2)
    if total_rev <= 0:
        return {'revenue_usd': 0.0, 'labor_cost_usd': round(total_labor, 2),
                'labor_to_revenue_pct': None, 'threshold_pct': int(threshold * 100)}
    ratio = total_labor / total_rev
    meta = {'revenue_usd': round(total_rev, 2), 'labor_cost_usd': round(total_labor, 2),
            'labor_to_revenue_pct': _number(round(ratio * 100, 2)),
            'threshold_pct': int(threshold * 100), 'labor_cap_at_threshold_usd': cap_30}
    if ratio > threshold:
        return {**meta, 'over_labor_vs_target_usd': round(total_labor - cap_30, 2)}
    return {**meta, 'headroom_under_cap_usd': round(cap_30 - total_labor, 2)}
