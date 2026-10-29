from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.models.models import SessionLocal, Labor
from app.core.security import get_restaurant_id
from app.core.ingestion_logger import log_ingestion

router = APIRouter()


class LaborItem(BaseModel):
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    hours_worked: float = Field(..., ge=0, description="Number of hours worked")
    total_labor_cost: float = Field(..., ge=0, description="Total labor cost for the day")


class LaborPayload(BaseModel):
    labor: List[LaborItem] = Field(..., min_items=1, description="List of labor data")


@router.post("/data/labor")
def create_labor_data(payload: LaborPayload, restaurant_id: int = Depends(get_restaurant_id)):
    """
    Accept labor data and insert into database.
    
    Args:
        payload: JSON payload containing labor data
        restaurant_id: Restaurant ID from API key authentication
        
    Returns:
        JSON response with status and number of rows inserted
    """
    session = None
    try:
        session = SessionLocal()
        rows_inserted = 0
        
        for labor_item in payload.labor:
            # Validate and parse date
            try:
                parsed_date = datetime.strptime(labor_item.date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid date format: {labor_item.date}. Expected YYYY-MM-DD"
                )
            
            # Check if labor data exists for this restaurant and date
            existing_labor = session.query(Labor).filter(
                Labor.restaurant_id == restaurant_id,
                Labor.date == parsed_date
            ).first()
            
            if existing_labor:
                # Update existing record
                existing_labor.hours_worked = labor_item.hours_worked
                existing_labor.total_labor_cost = labor_item.total_labor_cost
            else:
                # Create new record
                labor_record = Labor(
                    restaurant_id=restaurant_id,
                    date=parsed_date,
                    hours_worked=labor_item.hours_worked,
                    total_labor_cost=labor_item.total_labor_cost
                )
                session.add(labor_record)
            
            rows_inserted += 1
        
        # Commit all changes
        session.commit()
        
        # Log successful ingestion
        log_ingestion("labor", restaurant_id, rows_inserted, "success")
        
        return {
            "status": "success",
            "rows_inserted": rows_inserted
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        if session is not None:
            session.rollback()
        log_ingestion("labor", restaurant_id, 0, "error")
        raise
    except Exception:
        # Handle other exceptions
        if session is not None:
            session.rollback()
        log_ingestion("labor", restaurant_id, 0, "error")
        raise HTTPException(
            status_code=500,
            detail="DATA_INGESTION_UNAVAILABLE"
        )
    finally:
        if session is not None:
            session.close()
