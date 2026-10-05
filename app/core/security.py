import os

from fastapi import Header, HTTPException


def _load_api_keys() -> dict[str, int]:
    """
    Parse RORI_API_KEYS into an API key -> restaurant_id mapping.

    Format: comma-separated "key:restaurant_id" pairs, e.g. "abc123:1,def456:2".
    """
    raw = os.getenv("RORI_API_KEYS", "").strip()
    if not raw:
        raise HTTPException(
            status_code=500,
            detail="API key authentication is not configured (RORI_API_KEYS is not set)",
        )

    mapping: dict[str, int] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        key, sep, restaurant_id = entry.rpartition(":")
        if not sep or not key or not restaurant_id.strip().isdigit():
            raise HTTPException(
                status_code=500,
                detail="RORI_API_KEYS is malformed; expected 'key:restaurant_id' pairs",
            )
        mapping[key.strip()] = int(restaurant_id)
    return mapping


def verify_api_key(api_key: str) -> int:
    """
    Verify API key and return associated restaurant_id.
    
    Args:
        api_key: API key from request header
        
    Returns:
        Restaurant ID associated with the API key
        
    Raises:
        HTTPException: If API key is invalid or API keys are not configured
    """
    valid_api_keys = _load_api_keys()
    if api_key in valid_api_keys:
        return valid_api_keys[api_key]
    
    raise HTTPException(
        status_code=401,
        detail="Invalid API key"
    )


def get_restaurant_id(api_key: str = Header(..., alias="X-API-Key")):
    """
    FastAPI dependency to extract and verify API key from header.
    
    Args:
        api_key: API key from X-API-Key header
        
    Returns:
        Restaurant ID if key is valid
        
    Raises:
        HTTPException: If API key is invalid
    """
    return verify_api_key(api_key)
