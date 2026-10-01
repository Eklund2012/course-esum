from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from course_esum.config import get_settings
from course_esum.core.database import init_db
from course_esum.core.startup import sweep_orphaned_jobs
from course_esum.api.v1.router import v1_router
from course_esum.api.v1.endpoints import health

settings = get_settings()

# Path to bundled static assets (style.css, app.js, index.html)
STATIC_DIR = Path(__file__).resolve().parent / "static"

# Rate limiting
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_PER_MINUTE])

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables are created
    init_db()
    sweep_orphaned_jobs()
    yield
    # Shutdown logic if needed

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Automated university course evaluation analysis and summarization service powered by Google Gemini.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Attach state and exception handler for rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Middleware (permitting web clients like Next.js / React)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Health and Probes at root level
app.include_router(health.router)

# Mount Versioned API
app.include_router(v1_router, prefix="/api/v1")

# Serve static assets (CSS, JS)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Serve the web front-end at the root URL
@app.get("/", include_in_schema=False)
def root():
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("course_esum.main:app", host="0.0.0.0", port=8000, reload=True)
