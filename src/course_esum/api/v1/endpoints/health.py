from fastapi import APIRouter, Depends
from sqlmodel import Session, text
from course_esum.api.dependencies import get_db
from course_esum.config import get_settings

router = APIRouter(tags=["Health"])

@router.get("/healthz", summary="Liveness probe")
def health_check():
    """Returns basic service health status."""
    return {"status": "ok", "service": "course-esum"}

@router.get("/readyz", summary="Readiness probe")
def readiness_check(session: Session = Depends(get_db)):
    """Verifies database connectivity and configuration readiness."""
    settings = get_settings()
    
    # Check DB
    db_ok = False
    try:
        session.exec(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    ai_configured = bool(settings.GEMINI_API_KEY)

    ready = db_ok and ai_configured
    status_code = 200 if ready else 503

    return {
        "status": "ready" if ready else "not_ready",
        "database": "connected" if db_ok else "unreachable",
        "gemini_ai": "configured" if ai_configured else "missing_key",
        "version": settings.APP_VERSION
    }
