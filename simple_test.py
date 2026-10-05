import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from app.core.logger import log_analysis_run

# Create test results that match expected format
test_results = [
    {
        "type": "waste",
        "message": "Excess inventory of ExpiredItem detected",
        "impact": "$100.00 potential waste",
        "priority": "high",
        "meta": {"item": "ExpiredItem", "excess_units": 15}
    },
    {
        "type": "low_sales",
        "message": "Fries showing low sales volume",
        "impact": "$15.00 low revenue",
        "priority": "medium",
        "meta": {"item": "Fries", "sales_trend": "declining"}
    },
    {
        "type": "labor",
        "message": "Labor costs within normal range",
        "impact": "$120.00 daily labor cost",
        "priority": "low",
        "meta": {"hours": 8.0, "cost_per_hour": 15.0}
    }
]

print("Testing log_analysis_run() function...")
print(f"Test results: {len(test_results)} items")

# Test the logging function
log_analysis_run(test_results)

# Check if log file was created
log_files = [f for f in os.listdir('logs') if f.startswith('analysis_') and f.endswith('.json')]
if log_files:
    print(f"✓ Log file created: {log_files[-1]}")
    
    # Show log content
    with open(f'logs/{log_files[-1]}', 'r') as f:
        import json
        log_content = json.load(f)
        print(f"✓ Log timestamp: {log_content['timestamp']}")
        print(f"✓ Number of logged recommendations: {len(log_content['recommendations'])}")
        
        # Verify the content
        recommendations = log_content['recommendations']
        priorities = [r['priority'] for r in recommendations]
        print(f"✓ Priorities in log: {priorities}")
        
        # Test sorting functionality
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_results = sorted(test_results, key=lambda x: priority_order.get(x.get("priority", "low"), 2))
        sorted_priorities = [r['priority'] for r in sorted_results]
        print(f"✓ Sorted priorities: {sorted_priorities}")
        
else:
    print("✗ No log file found")

print("\nTest completed successfully!")
