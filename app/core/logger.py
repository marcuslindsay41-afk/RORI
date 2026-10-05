import json
import datetime
import os


def log_analysis_run(results: list):
    """
    Save analysis results to a JSON file in the logs directory.
    
    Args:
        results: List of analysis results to log
    """
    # Ensure logs directory exists
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)
    
    # Generate timestamp for filename
    now = datetime.datetime.now()
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    filename = f"analysis_{timestamp_str}.json"
    filepath = os.path.join(logs_dir, filename)
    
    # Create log data structure
    log_data = {
        "timestamp": now.isoformat(),
        "recommendations": results
    }
    
    # Save to JSON file
    with open(filepath, 'w') as f:
        json.dump(log_data, f, indent=2)
