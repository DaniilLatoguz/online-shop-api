"""Application-level behaviour that needs no database: error format, OpenAPI contract, health."""

from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.exceptions import AppError
from app.db.session import get_session
from app.main import create_app

PROBLEM_JSON = "application/problem+json"


async def test_unknown_route_returns_problem_404() -> None:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        response = await c.get("/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "not_found"


async def test_wrong_method_returns_problem_405_with_allow_header() -> None:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        response = await c.delete("/products")

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"
    assert response.headers["allow"]  # headers of the framework error are preserved


async def test_unexpected_error_returns_generic_500_without_internals() -> None:
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("database password is hunter2")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "hunter2" not in response.text


async def test_unknown_domain_error_category_defaults_to_400() -> None:
    class StrangeError(AppError):
        code = "strange"

    app = create_app()

    @app.get("/strange")
    async def strange() -> None:
        raise StrangeError("Something strange happened.")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/strange")

    assert response.status_code == 400
    assert response.json()["code"] == "strange"


async def test_health_returns_503_when_database_is_unreachable() -> None:
    unreachable = create_async_engine(
        "postgresql+asyncpg://user:password@127.0.0.1:1/db", poolclass=NullPool
    )
    session_factory = async_sessionmaker(unreachable)

    async def broken_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = broken_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/health")
    await unreachable.dispose()

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}


def test_openapi_offers_null_in_product_patch_only_where_it_is_accepted() -> None:
    # PATCH /products rejects null for name, price and stock (422), so the schema must not offer
    # it to generated clients. For description null is valid: it clears the text.
    properties = create_app().openapi()["components"]["schemas"]["ProductUpdate"]["properties"]

    nullable = {
        field: any(variant.get("type") == "null" for variant in schema.get("anyOf", [schema]))
        for field, schema in properties.items()
    }

    assert nullable == {"name": False, "description": True, "price": False, "stock": False}
