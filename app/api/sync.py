from datetime import datetime
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.models import SessionLocal, Sales, Inventory, Labor
from app.core.security import get_restaurant_id
from app.core.ingestion_logger import log_ingestion

router = APIRouter()


class SaleItem(BaseModel):
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    item_name: str = Field(..., min_length=1, description="Name of item sold")
    quantity_sold: int = Field(..., ge=0, description="Quantity of items sold")
    revenue: float = Field(..., ge=0, description="Total revenue from this sale")


class InventoryItem(BaseModel):
    item_name: str = Field(..., min_length=1, description="Name of inventory item")
    quantity_in_stock: int = Field(..., ge=0, description="Quantity of items in stock")
    cost_per_unit: float = Field(..., ge=0, description="Cost per unit")


class LaborItem(BaseModel):
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    hours_worked: float = Field(..., ge=0, description="Number of hours worked")
    total_labor_cost: float = Field(..., ge=0, description="Total labor cost for the day")


class SyncPayload(BaseModel):
    sales: List[SaleItem] = Field(default=[], description="List of sales data")
    inventory: List[InventoryItem] = Field(default=[], description="List of inventory data")
    labor: List[LaborItem] = Field(default=[], description="List of labor data")


@router.post("/data/sync")
def sync_restaurant_data(
    payload: SyncPayload, 
    restaurant_id: int = Depends(get_restaurant_id)
):
    """
    Accept combined sales, inventory, and labor data and sync to database.
    
    Args:
        payload: JSON payload containing sales, inventory, and labor data
        restaurant_id: Restaurant ID from API key authentication
        
    Returns:
        JSON response with status and counts of rows processed
    """
    session = None
    try:
        session = SessionLocal()
        sales_rows = 0
        inventory_rows = 0
        labor_rows = 0
        
        # Process sales data
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
            sales_rows += 1
        
        # Process inventory data
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
            
            inventory_rows += 1
        
        # Process labor data
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
            
            labor_rows += 1
        
        # Commit all changes
        session.commit()
        
        # Log successful ingestion for each data type
        if sales_rows > 0:
            log_ingestion("pos", restaurant_id, sales_rows, "success")
        if inventory_rows > 0:
            log_ingestion("inventory", restaurant_id, inventory_rows, "success")
        if labor_rows > 0:
            log_ingestion("labor", restaurant_id, labor_rows, "success")
        
        return {
            "status": "success",
            "sales_rows": sales_rows,
            "inventory_rows": inventory_rows,
            "labor_rows": labor_rows
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        if session is not None:
            session.rollback()
        log_ingestion("sync", restaurant_id, 0, "error")
        raise
    except Exception:
        # Handle other exceptions
        if session is not None:
            session.rollback()
        log_ingestion("sync", restaurant_id, 0, "error")
        raise HTTPException(
            status_code=500,
            detail="DATA_INGESTION_UNAVAILABLE"
        )
    finally:
        if session is not None:
            session.close()
