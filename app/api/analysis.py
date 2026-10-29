from fastapi import APIRouter, HTTPException

from app.core.recommendation_containment import OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE

router = APIRouter()


@router.post("/run-analysis/{restaurant_id}")
def post_run_analysis(restaurant_id: int):
    """Both registered aliases are unconditionally unavailable."""
    raise HTTPException(status_code=503, detail=OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE)
