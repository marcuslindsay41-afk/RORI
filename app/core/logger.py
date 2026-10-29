"""Legacy recommendation persistence is unavailable; existing logs are untouched."""
from app.core.recommendation_containment import deny_operational_recommendations


def log_analysis_run(results: list):
    deny_operational_recommendations()
