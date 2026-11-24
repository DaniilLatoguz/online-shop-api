"""Fixtures for integration tests: a real PostgreSQL database, migrated with Alembic.

The test database is `<POSTGRES_DB>_test` on the same server as the application database. It is
re-created at the start of every test run, so the migrations themselves are tested as well.
Tests commit for real (no transaction rollback tricks): this is what makes the concurrency tests
meaningful. Isolation comes from truncating all tables before each test.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Connection, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.session import get_session
from app.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TABLES = ("order_items", "orders", "cart_items", "products", "users")


def build_test_database_url(suffix: str = "_test") -> URL:
    settings = get_settings()
    return settings.database_url.set(database=f"{settings.postgres_db}{suffix}")


async def recreate_database(url: URL) -> None:
    """Drop (if needed) and create the database, via the `postgres` maintenance database."""
    admin_engine = create_async_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    async with admin_engine.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        await connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    await admin_engine.dispose()


async def drop_database(url: URL) -> None:
    admin_engine = create_async_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    async with admin_engine.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
    await admin_engine.dispose()


def run_alembic(connection: Connection, revision: str, *, downgrade: bool = False) -> None:
    """Run Alembic on an already open connection (see `alembic/env.py`)."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False
    if downgrade:
        command.downgrade(config, revision)
    else:
        command.upgrade(config, revision)


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    url = build_test_database_url()
    await recreate_database(url)
    test_engine = create_async_engine(url)
    async with test_engine.begin() as connection:
        await connection.run_sync(run_alembic, "head")
    yield test_engine
    await test_engine.dispose()


@pytest.fixture(autouse=True)
async def clean_database(engine: AsyncEngine) -> None:
    """Every test starts with empty tables and ids starting from 1."""
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """HTTP client calling the real application in-process, wired to the test database."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def get_test_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = get_test_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
