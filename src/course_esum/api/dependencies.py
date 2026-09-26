from typing import Generator
from fastapi import Depends
from sqlmodel import Session
from course_esum.core.database import get_session
from course_esum.core.security import verify_api_key

def get_db() -> Generator[Session, None, None]:
    """Dependency for obtaining an active database session."""
    yield from get_session()

AuthDep = Depends(verify_api_key)
DbDep = Depends(get_db)
