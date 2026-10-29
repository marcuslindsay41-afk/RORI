"""Legacy operational simulation is blocked before seeding, printing or threading."""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.recommendation_containment import deny_operational_recommendations


def simulate_restaurant(restaurant_id: int):
    deny_operational_recommendations()


def simulate_restaurants():
    deny_operational_recommendations()


def simulate_restaurants_concurrent():
    deny_operational_recommendations()


if __name__ == "__main__":
    simulate_restaurants_concurrent()
