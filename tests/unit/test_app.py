"""Application-level behaviour that needs no database: error format, OpenAPI contract, health."""

from httpx import ASGITransport, AsyncClient

from app.core.exceptions import AppError
from app.main import create_app

PROBLEM_JSON = "application/problem+json"


async def test_unknown_route_returns_problem_404() -> None:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        response = await c.get("/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "not_found"


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
