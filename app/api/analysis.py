from fastapi import APIRouter, HTTPException

from app.services.analysis_service import run_full_analysis

router = APIRouter()


@router.post("/run-analysis/{restaurant_id}")
def post_run_analysis(restaurant_id: int):
    """
    Run analysis for a specific restaurant.
    
    Args:
        restaurant_id: ID of the restaurant to analyze
        
    Returns:
        JSON response with restaurant_id and recommendations
    """
    try:
        results = run_full_analysis(restaurant_id)
        return {
            "restaurant_id": restaurant_id,
            "recommendations": results
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed for restaurant {restaurant_id}: {str(e)}"
        )
