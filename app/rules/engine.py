"""Legacy recommendation interfaces are closed, including private aggregation helpers.

Numerical diagnostics live in calculations.py and accept numbers, never a session.
There is no database/model import or alternate operational generation function here.
"""
from app.core.recommendation_containment import deny_operational_recommendations


def check_waste(session, restaurant_id: int):
    deny_operational_recommendations()


def low_performing_items(session, restaurant_id: int):
    deny_operational_recommendations()


def labor_efficiency(session, restaurant_id: int):
    deny_operational_recommendations()


def run_all_rules(session, restaurant_id: int):
    deny_operational_recommendations()


def _worst_impact(recs):
    deny_operational_recommendations()


def _format_public_impact(level):
    deny_operational_recommendations()


def _combine_messages(recs, empty_fallback):
    deny_operational_recommendations()


def _waste_rule_meta(recs):
    deny_operational_recommendations()


def _merge_low_sales_meta(recs):
    deny_operational_recommendations()


def _merge_labor_meta(recs):
    deny_operational_recommendations()
