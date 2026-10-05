import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

# Mock the database components to test without a real database
class MockSession:
    def query(self, model):
        # Return mock data that would normally come from database
        if hasattr(model, '__tablename__'):
            if model.__tablename__ == "sales":
                return [
                    type('MockSale', (), {
                        'item_name': 'Burger', 
                        'quantity_sold': 50, 
                        'revenue': 250.0
                    })(),
                    type('MockSale', (), {
                        'item_name': 'Fries', 
                        'quantity_sold': 5, 
                        'revenue': 15.0
                    })()
                ]
            elif model.__tablename__ == "inventory":
                return [
                    type('MockInventory', (), {
                        'item_name': 'Burger',
                        'quantity_in_stock': 100,
                        'cost_per_unit': 2.0
                    })(),
                    type('MockInventory', (), {
                        'item_name': 'ExpiredItem',
                        'quantity_in_stock': 20,
                        'cost_per_unit': 5.0
                    })()
                ]
            elif model.__tablename__ == "labor":
                return [
                    type('MockLabor', (), {
                        'date': '2024-01-01',
                        'hours_worked': 8.0,
                        'total_labor_cost': 120.0
                    })()
                ]
        return []
    
    def close(self):
        pass

# Mock SessionLocal to return our mock session
def mock_session_local():
    return MockSession()

# Temporarily replace SessionLocal
import app.services.analysis_service
original_session_local = app.services.analysis_service.SessionLocal
app.services.analysis_service.SessionLocal = mock_session_local

try:
    from app.services.analysis_service import run_full_analysis
    
    print("Testing run_full_analysis()...")
    results = run_full_analysis()
    
    print(f"Results: {results}")
    print(f"Number of results: {len(results)}")
    
    # Check if results are sorted by priority
    priorities = [r.get('priority', 'low') for r in results]
    print(f"Priorities: {priorities}")
    
    # Check if a log file was created
    import os
    log_files = [f for f in os.listdir('logs') if f.startswith('analysis_') and f.endswith('.json')]
    if log_files:
        print(f"Log file created: {log_files[-1]}")
        
        # Show log content
        with open(f'logs/{log_files[-1]}', 'r') as f:
            import json
            log_content = json.load(f)
            print(f"Log timestamp: {log_content['timestamp']}")
            print(f"Number of logged recommendations: {len(log_content['recommendations'])}")
    else:
        print("No log file found")
        
    print("\nTest completed successfully!")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

finally:
    # Restore original SessionLocal
    app.services.analysis_service.SessionLocal = original_session_local
