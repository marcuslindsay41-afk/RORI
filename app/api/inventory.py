from typing import List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.models import SessionLocal, Inventory
from app.core.security import get_restaurant_id
from app.core.ingestion_logger import log_ingestion

router = APIRouter()


class InventoryItem(BaseModel):
    item_name: str = Field(..., min_length=1, description="Name of the inventory item")
    quantity_in_stock: int = Field(..., ge=0, description="Quantity of items in stock")
    cost_per_unit: float = Field(..., ge=0, description="Cost per unit")


class InventoryPayload(BaseModel):
    inventory: List[InventoryItem] = Field(..., min_items=1, description="List of inventory data")


@router.post("/data/inventory")
def upsert_inventory(payload: InventoryPayload, restaurant_id: int = Depends(get_restaurant_id)):
    """
    Accept inventory data and upsert into database.
    
    Args:
        payload: JSON payload containing inventory data
        restaurant_id: Restaurant ID from API key authentication
        
    Returns:
        JSON response with status and number of rows updated
    """
    session = None
    try:
        session = SessionLocal()
        rows_updated = 0
        
        for item in payload.inventory:
            # Check if inventory item exists for this restaurant
            existing_item = session.query(Inventory).filter(
                Inventory.restaurant_id == restaurant_id,
                Inventory.item_name == item.item_name
            ).first()
            
            if existing_item:
                # Update existing record
                existing_item.quantity_in_stock = item.quantity_in_stock
                existing_item.cost_per_unit = item.cost_per_unit
            else:
                # Create new record
                inventory_record = Inventory(
                    restaurant_id=restaurant_id,
                    item_name=item.item_name,
                    quantity_in_stock=item.quantity_in_stock,
                    cost_per_unit=item.cost_per_unit
                )
                session.add(inventory_record)
            
            rows_updated += 1
        
        # Commit all changes
        session.commit()
        
        # Log successful ingestion
        log_ingestion("inventory", restaurant_id, rows_updated, "success")
        
        return {
            "status": "success",
            "rows_updated": rows_updated
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        if session is not None:
            session.rollback()
        log_ingestion("inventory", restaurant_id, 0, "error")
        raise
    except Exception:
        # Handle other exceptions
        if session is not None:
            session.rollback()
        log_ingestion("inventory", restaurant_id, 0, "error")
        raise HTTPException(
            status_code=500,
            detail="DATA_INGESTION_UNAVAILABLE"
        )
    finally:
        if session is not None:
            session.close()
