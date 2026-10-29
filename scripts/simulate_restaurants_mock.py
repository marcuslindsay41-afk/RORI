"""Synthetic scenarios cannot bypass operational containment or write analysis logs."""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.recommendation_containment import deny_operational_recommendations


def mock_seed_database():
    deny_operational_recommendations()


def mock_run_full_analysis():
    deny_operational_recommendations()


def simulate_restaurants():
    deny_operational_recommendations()


if __name__ == "__main__":
    simulate_restaurants()
