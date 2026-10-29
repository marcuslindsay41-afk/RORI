"""Legacy operational services are unavailable, including direct/background calls.

Do not import database, rule or logging dependencies here: denial must not require
healthy dependencies, and there is no fallback or production-enabling switch.
"""
from app.core.recommendation_containment import deny_operational_recommendations


def run_analysis(restaurant_id: int):
    deny_operational_recommendations()


def run_full_analysis(restaurant_id: int):
    deny_operational_recommendations()


def run_background_analysis(restaurant_id: int):
    deny_operational_recommendations()


def get_latest_recommendations(restaurant_id: int):
    deny_operational_recommendations()
