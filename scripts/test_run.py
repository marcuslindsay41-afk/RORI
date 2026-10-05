import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.analysis_service import run_analysis
from scripts.seed_data import seed_database

EXPECTED_TYPES = ("waste", "low_sales", "labor")
REQUIRED_KEYS = frozenset({"type", "message", "impact", "priority", "meta"})
VALID_TYPES = {"waste", "low_sales", "labor"}
VALID_PRIORITIES = frozenset({"high", "medium", "low"})


def verify_recommendations_format(recs: object) -> None:
    """Ensure output matches expected JSON shape:
    [
      {"type": "waste", "message": "...", "impact": "...", "priority": "...", "meta": {...}},
      ...
    ]
    """
    if not isinstance(recs, list):
        raise AssertionError(f"expected list, got {type(recs).__name__}")
    if len(recs) != 3:
        raise AssertionError(f"expected 3 recommendation objects, got {len(recs)}")
    for i, item in enumerate(recs):
        if not isinstance(item, dict):
            raise AssertionError(f"item {i}: expected dict, got {type(item).__name__}")
        if set(item.keys()) != REQUIRED_KEYS:
            raise AssertionError(
                f"item {i}: keys {sorted(item.keys())} != {sorted(REQUIRED_KEYS)}"
            )
        if item["type"] != EXPECTED_TYPES[i]:
            raise AssertionError(
                f"item {i}: type {item['type']!r} != {EXPECTED_TYPES[i]!r}"
            )
        if not isinstance(item["message"], str) or not item["message"]:
            raise AssertionError(f"item {i}: message must be a non-empty string")
        if not isinstance(item["impact"], str) or not item["impact"]:
            raise AssertionError(f"item {i}: impact must be a non-empty string")
        if item["priority"] not in VALID_PRIORITIES:
            raise AssertionError(
                f"item {i}: priority {item['priority']!r} must be one of {sorted(VALID_PRIORITIES)}"
            )
        if not isinstance(item["meta"], dict):
            raise AssertionError(f"item {i}: meta must be a dict")

    for rec in recs:
        assert rec["type"] in VALID_TYPES
        assert "$" in rec["impact"] or "cost" in rec["impact"].lower()


def main() -> None:
    seed_database(1)
    recommendations = run_analysis(1)
    print(json.dumps(recommendations, indent=2))
    verify_recommendations_format(recommendations)
    print("\nOK: output matches expected JSON format.")


if __name__ == "__main__":
    main()
