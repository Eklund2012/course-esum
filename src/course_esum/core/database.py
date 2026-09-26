from typing import Generator
from sqlmodel import SQLModel, create_engine, Session
from course_esum.config import get_settings

settings = get_settings()

# For SQLite, check_same_thread=False is needed for multi-threaded / async FastAPI
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args
)

def init_db() -> None:
    """Create all tables defined in SQLModel metadata."""
    SQLModel.metadata.create_all(engine)

def get_session() -> Generator[Session, None, None]:
    """Dependency that yields a database session."""
    with Session(engine) as session:
        yield session
