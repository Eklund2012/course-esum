from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from course_esum.config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    settings = get_settings()
    
    # In development mode, if no key header is passed, accept if API_KEY is empty or default
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'X-API-Key' authentication header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key provided.",
        )
        
    return api_key
