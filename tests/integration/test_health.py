import asyncio
import time
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.routes import health as health_module
from app.core.config import get_settings
from app.db.session import get_session
from app.main import create_app


async def test_health_reports_database_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def get_health(database_url: URL) -> Response:
    """Call /health with the application connected to the given database URL."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine)

    async def session_for_url() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = session_for_url
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            return await client.get("/health")
    finally:
        await engine.dispose()


async def test_health_returns_503_when_postgresql_rejects_the_connection() -> None:
    # The server is up but refuses the connection: asyncpg raises its own error
    # (InvalidCatalogNameError), the same way as for a wrong password or a starting server.
    url = get_settings().database_url.set(database="shop_no_such_database")

    response = await get_health(url)

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}


async def test_health_check_gives_up_after_the_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A server that accepts the connection but never answers must not hang the health check."""
    connections: list[asyncio.StreamWriter] = []

    async def never_answer(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connections.append(writer)  # keep the connection open and send nothing

    server = await asyncio.start_server(never_answer, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    monkeypatch.setattr(health_module, "HEALTH_CHECK_TIMEOUT_SECONDS", 0.2)
    started = time.monotonic()
    try:
        response = await get_health(get_settings().database_url.set(host="127.0.0.1", port=port))
    finally:
        for writer in connections:
            writer.close()
        server.close()
        await server.wait_closed()

    assert response.status_code == 503
    assert time.monotonic() - started < 2
