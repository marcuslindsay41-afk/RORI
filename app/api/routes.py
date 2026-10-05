from fastapi import APIRouter

from app.services.analysis_service import run_analysis
from app.api.analysis import router as analysis_router

router = APIRouter()

_last_analysis_results: list | None = None


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/run-analysis")
def post_run_analysis():
    global _last_analysis_results
    _last_analysis_results = run_analysis(1)  # Default to restaurant 1
    return _last_analysis_results


@router.get("/recommendations")
def get_recommendations():
    return _last_analysis_results


# Include the new analysis router
router.include_router(analysis_router, prefix="/analysis", tags=["analysis"])
