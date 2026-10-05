def flatten_recommendation(rec: dict) -> dict:
    """
    Flatten a recommendation dictionary into a single-level dict.
    
    Args:
        rec: Recommendation dictionary with potentially nested 'meta' field
        
    Returns:
        Flattened dictionary with meta fields prefixed with 'meta_'
    """
    if not isinstance(rec, dict):
        return {}
    
    # Start with top-level fields (excluding meta)
    flat_dict = {}
    for key, value in rec.items():
        if key != 'meta':
            flat_dict[key] = value
    
    # Flatten meta fields if they exist
    if 'meta' in rec and isinstance(rec['meta'], dict):
        meta_fields = _flatten_dict(rec['meta'], 'meta_')
        flat_dict.update(meta_fields)
    
    return flat_dict


def _flatten_dict(d: dict, prefix: str = '') -> dict:
    """
    Recursively flatten a dictionary with the given prefix.
    
    Args:
        d: Dictionary to flatten
        prefix: Key prefix to add to each flattened key
        
    Returns:
        Flattened dictionary
    """
    if not isinstance(d, dict):
        return {}
    
    result = {}
    for key, value in d.items():
        new_key = f"{prefix}{key}"
        
        if isinstance(value, dict):
            # Recursively flatten nested dictionaries
            nested = _flatten_dict(value, f"{new_key}_")
            result.update(nested)
        else:
            result[new_key] = value
    
    return result
