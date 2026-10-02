"""Pytest fixtures: in-memory sqlite + TestClient, no Postgres required.

The app lifespan references module globals app.main.engine / SessionLocal
(dependency injection does not apply inside lifespan), so both are rebound to
the test engine at import time. Route handlers get their sessions through the
get_db dependency override.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main
from app.database import Base, get_db
from app.services.seed import seed_if_empty

test_engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

# Rebind the names the lifespan closure actually looks up.
main.engine = test_engine
main.SessionLocal = TestSessionLocal


def _override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


main.app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    session = TestSessionLocal()
    seed_if_empty(session)
    session.close()
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def session_factory(client):
    """Depends on `client` so schema/seed setup runs first; hands out sessions
    for tests that need to seed extra rows straight into the DB."""
    return TestSessionLocal
