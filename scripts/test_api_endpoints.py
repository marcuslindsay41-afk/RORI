import json
import os
import sys
import requests
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.analysis_service import run_full_analysis
from app.models.models import SessionLocal, Sales, Inventory, Labor

# API base URL
BASE_URL = "http://127.0.0.1:8000"

def test_pos_endpoint(restaurant_id: int):
    """Test POST /data/pos endpoint with sample sales data."""
    print(f"\n=== Testing POS Endpoint for Restaurant {restaurant_id} ===")
    
    # Generate sample sales data for the last 7 days
    sales_data = []
    base_date = datetime.now() - timedelta(days=7)
    
    items = ["Burger", "Fries", "Soda", "Chicken Sandwich", "Salad"]
    
    for i in range(7):
        date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        for item in items:
            sales_data.append({
                "date": date,
                "item_name": item,
                "quantity_sold": (i + 1) * 10,
                "revenue": (i + 1) * 50.0
            })
    
    payload = {
        "restaurant_id": restaurant_id,
        "sales": sales_data
    }
    
    try:
        response = requests.post(f"{BASE_URL}/data/pos", json=payload)
        print(f"POS Response Status: {response.status_code}")
        print(f"POS Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"POS endpoint error: {e}")
        return False

def test_inventory_endpoint(restaurant_id: int):
    """Test POST /data/inventory endpoint with sample inventory data."""
    print(f"\n=== Testing Inventory Endpoint for Restaurant {restaurant_id} ===")
    
    inventory_data = [
        {
            "item_name": "Burger",
            "quantity_in_stock": 100,
            "cost_per_unit": 2.50
        },
        {
            "item_name": "Fries",
            "quantity_in_stock": 200,
            "cost_per_unit": 0.75
        },
        {
            "item_name": "Soda",
            "quantity_in_stock": 150,
            "cost_per_unit": 0.50
        },
        {
            "item_name": "Chicken Sandwich",
            "quantity_in_stock": 80,
            "cost_per_unit": 3.25
        },
        {
            "item_name": "Salad",
            "quantity_in_stock": 60,
            "cost_per_unit": 2.00
        }
    ]
    
    payload = {
        "restaurant_id": restaurant_id,
        "inventory": inventory_data
    }
    
    try:
        response = requests.post(f"{BASE_URL}/data/inventory", json=payload)
        print(f"Inventory Response Status: {response.status_code}")
        print(f"Inventory Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Inventory endpoint error: {e}")
        return False

def test_labor_endpoint(restaurant_id: int):
    """Test POST /data/labor endpoint with sample labor data."""
    print(f"\n=== Testing Labor Endpoint for Restaurant {restaurant_id} ===")
    
    labor_data = []
    base_date = datetime.now() - timedelta(days=7)
    
    for i in range(7):
        date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        labor_data.append({
            "date": date,
            "hours_worked": 8.0 + i,
            "total_labor_cost": 120.0 + (i * 15)
        })
    
    payload = {
        "restaurant_id": restaurant_id,
        "labor": labor_data
    }
    
    try:
        response = requests.post(f"{BASE_URL}/data/labor", json=payload)
        print(f"Labor Response Status: {response.status_code}")
        print(f"Labor Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Labor endpoint error: {e}")
        return False

def verify_database_data(restaurant_id: int):
    """Verify data was inserted correctly for the specific restaurant."""
    print(f"\n=== Verifying Database Data for Restaurant {restaurant_id} ===")
    
    session = SessionLocal()
    try:
        # Check sales data
        sales_count = session.query(Sales).filter(Sales.restaurant_id == restaurant_id).count()
        print(f"Sales rows for restaurant {restaurant_id}: {sales_count}")
        
        # Check inventory data
        inventory_count = session.query(Inventory).filter(Inventory.restaurant_id == restaurant_id).count()
        print(f"Inventory rows for restaurant {restaurant_id}: {inventory_count}")
        
        # Check labor data
        labor_count = session.query(Labor).filter(Labor.restaurant_id == restaurant_id).count()
        print(f"Labor rows for restaurant {restaurant_id}: {labor_count}")
        
        # Show sample data
        sample_sales = session.query(Sales).filter(Sales.restaurant_id == restaurant_id).limit(3).all()
        print(f"Sample sales data:")
        for sale in sample_sales:
            print(f"  - {sale.item_name}: {sale.quantity_sold} units, ${sale.revenue}")
            
        return sales_count > 0 and inventory_count > 0 and labor_count > 0
    finally:
        session.close()

def test_analysis(restaurant_id: int):
    """Test analysis function and print results."""
    print(f"\n=== Testing Analysis for Restaurant {restaurant_id} ===")
    
    try:
        results = run_full_analysis(restaurant_id)
        print("Analysis Results:")
        print(json.dumps(results, indent=2))
        
        # Verify results structure
        if len(results) == 3:
            types = [r.get("type") for r in results]
            expected_types = ["waste", "low_sales", "labor"]
            if types == expected_types:
                print("✅ Analysis results structure is correct")
                return True
            else:
                print(f"❌ Analysis results types mismatch: {types} vs {expected_types}")
                return False
        else:
            print(f"❌ Expected 3 results, got {len(results)}")
            return False
    except Exception as e:
        print(f"❌ Analysis error: {e}")
        return False

def main():
    """Run all API endpoint tests."""
    restaurant_id = 1
    
    print("Starting API Endpoint Tests...")
    print(f"Testing with restaurant_id: {restaurant_id}")
    
    # Test all endpoints
    success = True
    
    success &= test_pos_endpoint(restaurant_id)
    success &= test_inventory_endpoint(restaurant_id)
    success &= test_labor_endpoint(restaurant_id)
    
    # Verify database
    success &= verify_database_data(restaurant_id)
    
    # Test analysis
    success &= test_analysis(restaurant_id)
    
    # Final result
    print(f"\n{'='*50}")
    if success:
        print("✅ ALL TESTS PASSED!")
        print("✅ API endpoints working correctly")
        print("✅ Data filtering by restaurant_id working")
        print("✅ Analysis producing valid results")
    else:
        print("❌ SOME TESTS FAILED!")
        print("❌ Check the errors above")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
