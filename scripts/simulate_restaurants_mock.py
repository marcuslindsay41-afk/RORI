import time
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.logger import log_analysis_run


def mock_seed_database():
    """Mock database seeding - generates different test data for each restaurant."""
    print("  (mock) Seeding database with restaurant data...")


def mock_run_full_analysis():
    """Mock analysis that returns different results for each simulation run."""
    import random
    
    # Different scenarios for variety
    scenarios = [
        [
            {
                "type": "waste",
                "message": "Excess inventory of ExpiredIngredients detected",
                "impact": "$250.00 potential waste",
                "priority": "high",
                "meta": {"item": "ExpiredIngredients", "excess_units": 50}
            },
            {
                "type": "low_sales",
                "message": "PremiumBurger showing low sales volume",
                "impact": "$45.00 low revenue",
                "priority": "medium",
                "meta": {"item": "PremiumBurger", "sales_trend": "declining"}
            },
            {
                "type": "labor",
                "message": "Labor costs within normal range",
                "impact": "$320.00 daily labor cost",
                "priority": "low",
                "meta": {"hours": 16.0, "cost_per_hour": 20.0}
            }
        ],
        [
            {
                "type": "waste",
                "message": "Overstock of FrozenItems detected",
                "impact": "$180.00 potential waste",
                "priority": "high",
                "meta": {"item": "FrozenItems", "excess_units": 30}
            },
            {
                "type": "low_sales",
                "message": "DessertItems showing declining sales",
                "impact": "$25.00 low revenue",
                "priority": "medium",
                "meta": {"item": "DessertItems", "sales_trend": "declining"}
            },
            {
                "type": "labor",
                "message": "Labor costs slightly elevated",
                "impact": "$380.00 daily labor cost",
                "priority": "medium",
                "meta": {"hours": 19.0, "cost_per_hour": 20.0}
            }
        ],
        [
            {
                "type": "waste",
                "message": "FreshProduce approaching expiration",
                "impact": "$120.00 potential waste",
                "priority": "medium",
                "meta": {"item": "FreshProduce", "excess_units": 15}
            },
            {
                "type": "low_sales",
                "message": "BeverageItems showing low sales volume",
                "impact": "$35.00 low revenue",
                "priority": "medium",
                "meta": {"item": "BeverageItems", "sales_trend": "stable"}
            },
            {
                "type": "labor",
                "message": "Labor costs optimized",
                "impact": "$280.00 daily labor cost",
                "priority": "low",
                "meta": {"hours": 14.0, "cost_per_hour": 20.0}
            }
        ]
    ]
    
    # Return a random scenario
    return random.choice(scenarios)


def simulate_restaurants():
    """Simulate analysis for multiple restaurants."""
    print("Starting multi-restaurant simulation...")
    
    for i in range(1, 4):
        print(f"Simulating Restaurant {i}...")
        mock_seed_database()
        results = mock_run_full_analysis()
        
        # Sort results by priority (high -> medium -> low)
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_results = sorted(results, key=lambda x: priority_order.get(x.get("priority", "low"), 2))
        
        # Log the results
        log_analysis_run(sorted_results)
        
        # Print top recommendation
        if sorted_results:
            print(f"  Top recommendation: {sorted_results[0]['message']}")
            print(f"  Priority: {sorted_results[0]['priority']}")
            print(f"  Impact: {sorted_results[0]['impact']}")
        else:
            print("  No recommendations generated")
        
        time.sleep(2)
    
    print("Simulation complete")


if __name__ == "__main__":
    simulate_restaurants()
