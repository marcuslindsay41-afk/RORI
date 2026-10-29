from fastapi import APIRouter, HTTPException

from app.core.recommendation_containment import OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE
from app.api.analysis import router as analysis_router

router = APIRouter()

_last_analysis_results: list | None = None


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/run-analysis")
def post_run_analysis():
    raise HTTPException(status_code=503, detail=OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE)


@router.get("/recommendations")
def get_recommendations():
    raise HTTPException(status_code=503, detail=OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE)


# Include the new analysis router
router.include_router(analysis_router, prefix="/analysis", tags=["analysis"])
