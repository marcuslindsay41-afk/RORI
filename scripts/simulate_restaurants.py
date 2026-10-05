import time
import os
import sys
import json
from concurrent.futures import ThreadPoolExecutor

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.seed_data import seed_database
from app.services.analysis_service import run_full_analysis
from app.core.flatten import flatten_recommendation


def simulate_restaurant(restaurant_id: int):
    """Simulate analysis for a single restaurant."""
    print(f"Simulating Restaurant {restaurant_id}...")
    seed_database(restaurant_id)
    results = run_full_analysis(restaurant_id)
    if results:
        # Flatten each recommendation
        flattened_results = [flatten_recommendation(r) for r in results]
        print("Top recommendation (flattened):")
        print(json.dumps(flattened_results[0], indent=2))
    else:
        print("No recommendations generated")


def simulate_restaurants():
    """Simulate analysis for multiple restaurants sequentially."""
    print("Starting multi-restaurant simulation...")
    
    for i in range(1, 4):
        simulate_restaurant(i)
        time.sleep(2)
    
    print("Simulation complete")


def simulate_restaurants_concurrent():
    """Simulate analysis for multiple restaurants concurrently."""
    print("Starting concurrent multi-restaurant simulation...")
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        # Submit all restaurant simulations
        futures = [executor.submit(simulate_restaurant, i) for i in range(1, 4)]
        
        # Wait for all to complete
        for future in futures:
            future.result()
    
    print("Concurrent simulation complete")


if __name__ == "__main__":
    simulate_restaurants_concurrent()
