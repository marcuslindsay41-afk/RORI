import datetime
import json
import os


def log_ingestion(event_type: str, restaurant_id: int, rows: int, status: str):
    """
    Log data ingestion events to JSON file.
    
    Args:
        event_type: Type of ingestion event (pos, inventory, labor)
        restaurant_id: Restaurant ID that performed the ingestion
        rows: Number of rows processed
        status: Status of the ingestion (success, error)
    """
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)
    
    # Create filename with current date
    now = datetime.datetime.now()
    filename = f"ingestion_{now.strftime('%Y%m%d')}.json"
    filepath = os.path.join(logs_dir, filename)
    
    # Create log entry
    log_entry = {
        "timestamp": now.isoformat(),
        "event_type": event_type,
        "restaurant_id": restaurant_id,
        "rows": rows,
        "status": status
    }
    
    # Read existing logs or create new list
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                logs = json.load(f)
        else:
            logs = []
    except (json.JSONDecodeError, FileNotFoundError):
        logs = []
    
    # Add new entry
    logs.append(log_entry)
    
    # Write back to file
    with open(filepath, 'w') as f:
        json.dump(logs, f, indent=2)
