import os
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine, Session
from sqlmodel.pool import StaticPool
from unittest.mock import patch

from course_esum.main import app
from course_esum.core.database import get_session

TEST_API_KEY = "test-secret-key-999"


@pytest.fixture(name="session", scope="function")
def session_fixture():
    """In-memory SQLite database for isolated tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client", scope="function")
def client_fixture(session: Session):
    """
    TestClient with overridden DB session and API key.

    The Settings object is cached via lru_cache, so mutating the instance
    directly has no effect once the cache is populated. Instead we patch the
    underlying attribute on the cached object for the duration of each test.
    """
    from course_esum.config import get_settings

    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override

    # Patch the *cached* Settings instance so security checks use the test key
    with patch.object(get_settings(), "API_KEY", TEST_API_KEY):
        with TestClient(app) as test_client:
            yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(name="auth_headers")
def auth_headers_fixture():
    return {"X-API-Key": TEST_API_KEY}
