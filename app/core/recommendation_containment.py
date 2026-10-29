"""Unconditional legacy containment. No configuration or positive authorization."""
from typing import NoReturn

OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE = 'OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE'


class OperationalRecommendationsUnavailable(RuntimeError):
    """A blocked operation, never an empty or successful recommendation result."""


def deny_operational_recommendations() -> NoReturn:
    raise OperationalRecommendationsUnavailable(OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE)
