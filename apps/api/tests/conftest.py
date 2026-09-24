"""Tests de integración contra un Postgres real (base `globalai_test`).

Postgres real y no SQLite: usamos JSONB, índices parciales y ON CONFLICT, y queremos
probar exactamente lo que corre en producción.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://globalai:globalai@localhost:5432/globalai_test"
)
os.environ["ENV"] = "test"

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from seed.seed import DATA_DIR, seed_assessment, seed_catalog  # noqa: E402

STUDENT = {"email": "estudiante@globalai.demo", "password": "Demo1234!"}
TEACHER = {"email": "profesor@globalai.demo", "password": "Demo1234!"}
SLUG = "placement-a1-b2"


@pytest.fixture(scope="session", autouse=True)
async def database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session, session.begin():
        await seed_catalog(session)
        await seed_assessment(session, DATA_DIR / "placement_a1_b2.json")
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_attempts():
    yield
    async with engine.begin() as conn:
        await conn.execute(text("delete from attempts"))


@asynccontextmanager
async def _client(credentials: dict | None) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as client:
        if credentials:
            response = await client.post("/auth/login", json=credentials)
            assert response.status_code == 200, response.text
        yield client


@pytest.fixture
async def anon():
    async with _client(None) as c:
        yield c


@pytest.fixture
async def student():
    async with _client(STUDENT) as c:
        yield c


@pytest.fixture
async def teacher():
    async with _client(TEACHER) as c:
        yield c
