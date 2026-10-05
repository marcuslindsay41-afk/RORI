from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

import app.models.models as models

# Stock vs. sold: flag when on-hand units exceed this multiple of total units sold (period data).
_WASTE_STOCK_TO_SALES_RATIO = 3.0


def _worst_impact(recs: list[dict]) -> str:
    order = {"high": 3, "medium": 2, "low": 1}
    if not recs:
        return "low"
    return max((r.get("impact", "low") for r in recs), key=lambda x: order.get(x, 0))


def _format_public_impact(level: str) -> str:
    """Generalized, consistent impact line (not item-specific)."""
    mapping = {
        "high": "high cost exposure",
        "medium": "medium cost exposure",
        "low": "low cost exposure",
    }
    return mapping.get(level, f"{level} cost exposure")


def _combine_messages(recs: list[dict], empty_fallback: str) -> str:
    if not recs:
        return empty_fallback
    return "; ".join(r["message"] for r in recs)


def _waste_rule_meta(recs: list[dict]) -> dict:
    flags: list[dict] = []
    for r in recs:
        m = r.get("meta")
        if isinstance(m, dict):
            flags.append(m)
    if flags:
        return {"flags": flags}
    return {"flags": [], "status": "ok"}


def check_waste(session: Session, restaurant_id: int) -> list[dict]:
    """Compare inventory to sales; flag likely overstock / waste risk."""
    sold_rows = (
        session.query(
            models.Sales.item_name,
            func.coalesce(func.sum(models.Sales.quantity_sold), 0).label("sold"),
        )
        .filter(models.Sales.restaurant_id == restaurant_id)
        .group_by(models.Sales.item_name)
        .all()
    )
    sold_map = {row.item_name: int(row.sold) for row in sold_rows}

    recommendations: list[dict] = []
    for inv in session.query(models.Inventory).filter(models.Inventory.restaurant_id == restaurant_id).all():
        sold = sold_map.get(inv.item_name, 0)
        stock = inv.quantity_in_stock
        cost = float(inv.cost_per_unit)

        if sold == 0:
            if stock > 20:
                # Capital tied up + spoilage risk: rough weekly exposure
                est_weekly = round(stock * cost * 0.08, 2)
                recommendations.append(
                    {
                        "message": (
                            f"{inv.item_name}: no sales this period but {stock} units in stock "
                            f"(~${est_weekly}/wk estimated carrying/spoilage risk at ${cost:.2f}/unit); "
                            "pause reorders and clear stock before reordering."
                        ),
                        "impact": "high",
                        "meta": {
                            "item": inv.item_name,
                            "units_in_stock": stock,
                            "cost_per_unit_usd": round(cost, 2),
                            "estimated_weekly_loss_usd": est_weekly,
                            "overstock_pct": None,
                            "reason": "no_period_sales",
                        },
                    }
                )
            continue

        ratio = stock / sold
        if ratio >= _WASTE_STOCK_TO_SALES_RATIO:
            # Share of on-hand units not justified by period sales velocity
            excess_pct = int(round((stock - sold) / max(stock, 1) * 100))
            excess_pct = min(95, max(0, excess_pct))
            weekly_sold = sold / 2.0  # 14-day window ≈ 2 weeks
            ideal_ceiling = max(sold, weekly_sold * 2)
            excess_units = max(0, int(stock - ideal_ceiling))
            est_weekly = round(excess_units * cost * 0.15, 2)
            order_cut_pct = min(45, max(10, excess_pct // 2))

            recommendations.append(
                {
                    "message": (
                        f"{inv.item_name}: inventory exceeds usage vs this period's sales "
                        f"by ~{excess_pct}% of on-hand units ({stock} in stock vs {sold} sold); "
                        f"trim orders by ~{order_cut_pct}% to reduce waste (~${est_weekly}/wk risk at ${cost:.2f}/unit)."
                    ),
                    "impact": "medium",
                    "meta": {
                        "item": inv.item_name,
                        "units_in_stock": stock,
                        "units_sold_period": sold,
                        "stock_to_sales_ratio": round(ratio, 2),
                        "overstock_pct": excess_pct,
                        "cost_per_unit_usd": round(cost, 2),
                        "estimated_weekly_loss_usd": est_weekly,
                        "suggested_order_reduction_pct": order_cut_pct,
                    },
                }
            )
    return recommendations


def low_performing_items(session: Session, restaurant_id: int) -> list[dict]:
    """Surface items with the lowest total revenue with numeric context."""
    rows = (
        session.query(
            models.Sales.item_name,
            func.coalesce(func.sum(models.Sales.revenue), 0.0).label("rev"),
        )
        .filter(models.Sales.restaurant_id == restaurant_id)
        .group_by(models.Sales.item_name)
        .all()
    )
    if not rows:
        return [
            {
                "message": "No sales data to rank items.",
                "impact": "low",
                "meta": {"bottom_items": [], "avg_revenue_usd": None},
            }
        ]

    sorted_rows = sorted(rows, key=lambda r: float(r.rev))
    bottom = sorted_rows[:3]
    revs_all = [float(r.rev) for r in rows]
    avg_rev = sum(revs_all) / len(revs_all) if revs_all else 0.0
    bottom_items = []
    parts = []
    for r in bottom:
        rev = float(r.rev)
        pct_below = (
            round((avg_rev - rev) / avg_rev * 100, 0) if avg_rev > 0 else 0.0
        )
        bottom_items.append(
            {
                "item": r.item_name,
                "revenue_usd": round(rev, 2),
                "pct_below_period_avg": min(100.0, max(0.0, pct_below)),
            }
        )
        parts.append(
            f"{r.item_name} (~${rev:,.0f}, ~{pct_below:.0f}% below ${avg_rev:,.0f}/item avg)"
        )

    names_detail = "; ".join(parts)
    message = (
        f"Lowest revenue items this period: {names_detail}. "
        "Raise prices, bundle, feature on menu, or phase out slow movers."
    )

    return [
        {
            "message": message,
            "impact": "medium",
            "meta": {
                "bottom_items": bottom_items,
                "avg_revenue_usd": round(avg_rev, 2),
                "items_in_menu": len(rows),
            },
        }
    ]


def labor_efficiency(session: Session, restaurant_id: int) -> list[dict]:
    """Labor cost as share of revenue; flag if above 30%."""
    total_rev = session.query(func.coalesce(func.sum(models.Sales.revenue), 0.0)).filter(models.Sales.restaurant_id == restaurant_id).scalar()
    total_rev = float(total_rev or 0.0)
    total_labor = session.query(
        func.coalesce(func.sum(models.Labor.total_labor_cost), 0.0)
    ).filter(models.Labor.restaurant_id == restaurant_id).scalar()
    total_labor = float(total_labor or 0.0)

    threshold = 0.30
    cap_30 = round(total_rev * threshold, 2)

    if total_rev <= 0:
        return [
            {
                "message": (
                    "No revenue recorded ($0); cannot size labor vs sales — "
                    "enter sales or labor rows to get a dollar and % comparison."
                ),
                "impact": "high",
                "meta": {
                    "revenue_usd": 0.0,
                    "labor_cost_usd": round(total_labor, 2),
                    "labor_to_revenue_pct": None,
                    "threshold_pct": int(threshold * 100),
                },
            }
        ]

    ratio = total_labor / total_rev
    meta = {
        "revenue_usd": round(total_rev, 2),
        "labor_cost_usd": round(total_labor, 2),
        "labor_to_revenue_pct": round(ratio * 100, 2),
        "threshold_pct": int(threshold * 100),
        "labor_cap_at_threshold_usd": cap_30,
    }

    if ratio > threshold:
        over_by = round(total_labor - cap_30, 2)
        return [
            {
                "message": (
                    f"Labor was ${total_labor:,.0f} on ${total_rev:,.0f} revenue "
                    f"({ratio:.1%} vs {threshold:.0%} target); "
                    f"~${over_by:,.0f} over a healthy labor ceiling for this sales level — "
                    "cut hours, stagger shifts, or push revenue before adding labor."
                ),
                "impact": "high",
                "meta": {**meta, "over_labor_vs_target_usd": over_by},
            }
        ]
    headroom = round(cap_30 - total_labor, 2)
    return [
        {
            "message": (
                f"Labor ${total_labor:,.0f} vs ${total_rev:,.0f} revenue ({ratio:.1%}); "
                f"at or below {threshold:.0%} target (~${headroom:,.0f} under the ${cap_30:,.0f} labor ceiling)."
            ),
            "impact": "low",
            "meta": {**meta, "headroom_under_cap_usd": headroom},
        }
    ]


def _merge_low_sales_meta(recs: list[dict]) -> dict:
    for r in recs:
        m = r.get("meta")
        if isinstance(m, dict) and m:
            return m
    return {"bottom_items": [], "avg_revenue_usd": None}


def _merge_labor_meta(recs: list[dict]) -> dict:
    for r in recs:
        m = r.get("meta")
        if isinstance(m, dict) and m:
            return m
    return {}


def run_all_rules(session: Session, restaurant_id: int) -> list[dict]:
    """Fixed order: waste → low_sales → labor. impact = generalized; priority = urgency; message + meta = specifics."""
    waste_recs = check_waste(session, restaurant_id)
    low_recs = low_performing_items(session, restaurant_id)
    labor_recs = labor_efficiency(session, restaurant_id)

    w_priority = _worst_impact(waste_recs)
    l_priority = _worst_impact(low_recs)
    lab_priority = _worst_impact(labor_recs)

    waste_fallback = (
        "No inventory waste risk detected this period: stock levels look aligned with sales "
        "(no meaningful excess cost exposure)."
    )
    low_fallback = (
        "Not enough sales rows to rank items; add item-level sales to surface revenue laggards."
    )
    labor_fallback = (
        "No labor rows and/or revenue to score efficiency — add labor cost entries to compare vs revenue."
    )

    return [
        {
            "type": "waste",
            "message": _combine_messages(waste_recs, waste_fallback),
            "impact": _format_public_impact(w_priority),
            "priority": w_priority,
            "meta": _waste_rule_meta(waste_recs),
        },
        {
            "type": "low_sales",
            "message": _combine_messages(low_recs, low_fallback),
            "impact": _format_public_impact(l_priority),
            "priority": l_priority,
            "meta": _merge_low_sales_meta(low_recs),
        },
        {
            "type": "labor",
            "message": _combine_messages(labor_recs, labor_fallback),
            "impact": _format_public_impact(lab_priority),
            "priority": lab_priority,
            "meta": _merge_labor_meta(labor_recs),
        },
    ]
