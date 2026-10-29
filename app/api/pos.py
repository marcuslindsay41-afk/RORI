from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.models.models import SessionLocal, Sales
from app.core.security import get_restaurant_id
from app.core.ingestion_logger import log_ingestion

router = APIRouter()


class SaleItem(BaseModel):
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    item_name: str = Field(..., min_length=1, description="Name of the item sold")
    quantity_sold: int = Field(..., ge=0, description="Quantity of items sold")
    revenue: float = Field(..., ge=0, description="Total revenue from this sale")


class POSPayload(BaseModel):
    sales: List[SaleItem] = Field(..., min_items=1, description="List of sales data")


@router.post("/data/pos")
def create_pos_sales(payload: POSPayload, restaurant_id: int = Depends(get_restaurant_id)):
    """
    Accept POS sales data and insert into database.
    
    Args:
        payload: JSON payload containing sales data
        restaurant_id: Restaurant ID from API key authentication
        
    Returns:
        JSON response with status and number of rows inserted
    """
    session = None
    try:
        session = SessionLocal()
        rows_inserted = 0
        
        for sale in payload.sales:
            # Validate and parse date
            try:
                parsed_date = datetime.strptime(sale.date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid date format for item '{sale.item_name}': {sale.date}. Expected YYYY-MM-DD"
                )
            
            # Create sale record
            sale_record = Sales(
                restaurant_id=restaurant_id,
                date=parsed_date,
                item_name=sale.item_name,
                quantity_sold=sale.quantity_sold,
                revenue=sale.revenue
            )
            
            session.add(sale_record)
            rows_inserted += 1
        
        # Commit all changes
        session.commit()
        
        # Log successful ingestion
        log_ingestion("pos", restaurant_id, rows_inserted, "success")
        
        return {
            "status": "success",
            "rows_inserted": rows_inserted
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        if session is not None:
            session.rollback()
        log_ingestion("pos", restaurant_id, 0, "error")
        raise
    except Exception:
        # Handle other exceptions
        if session is not None:
            session.rollback()
        log_ingestion("pos", restaurant_id, 0, "error")
        raise HTTPException(
            status_code=500,
            detail="DATA_INGESTION_UNAVAILABLE"
        )
    finally:
        if session is not None:
            session.close()
