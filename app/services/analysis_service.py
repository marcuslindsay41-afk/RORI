from app.models.models import SessionLocal, engine
from app.rules.engine import run_all_rules
from app.core.logger import log_analysis_run
from typing import Optional
import threading


def run_analysis(restaurant_id: int):
    """Run analysis for a specific restaurant without logging."""
    session = SessionLocal()
    try:
        results = run_all_rules(session, restaurant_id)
        return results
    finally:
        session.close()


def run_full_analysis(restaurant_id: int):
    """
    Run full analysis for a specific restaurant with priority sorting and logging.
    
    Args:
        restaurant_id: ID of the restaurant to analyze
        
    Returns:
        List of priority-sorted recommendations with meta fields
    """
    session = SessionLocal()
    try:
        results = run_all_rules(session, restaurant_id)
        
        # Sort results by priority: high -> medium -> low
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_results = sorted(results, key=lambda x: priority_order.get(x.get("priority", "low"), 2))
        
        # Log the results
        log_analysis_run(sorted_results)
        
        return sorted_results
    finally:
        session.close()


def run_background_analysis(restaurant_id: int) -> threading.Thread:
    """
    Run analysis in background thread after data ingestion.
    
    Args:
        restaurant_id: ID of the restaurant to analyze
        
    Returns:
        Thread object for the background analysis
    """
    def background_task():
        try:
            run_full_analysis(restaurant_id)
        except Exception as e:
            # Log error but don't raise - background task should fail silently
            print(f"Background analysis failed for restaurant {restaurant_id}: {e}")
    
    thread = threading.Thread(target=background_task, daemon=True)
    thread.start()
    return thread


def get_latest_recommendations(restaurant_id: int) -> Optional[list]:
    """
    Get latest recommendations without running new analysis.
    Useful for quick lookups without triggering new calculations.
    
    Args:
        restaurant_id: ID of the restaurant
        
    Returns:
        List of recommendations or None if no data available
    """
    session = SessionLocal()
    try:
        results = run_all_rules(session, restaurant_id)
        
        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_results = sorted(results, key=lambda x: priority_order.get(x.get("priority", "low"), 2))
        
        return sorted_results
    except Exception:
        return None
    finally:
        session.close()
