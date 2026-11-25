"""Small helpers that keep the API tests short and readable."""

from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.constants import MAX_ITEM_QUANTITY

PROBLEM_JSON = "application/problem+json"


def as_user(user_id: int) -> dict[str, str]:
    return {"X-User-Id": str(user_id)}


def json_of(response: Response) -> dict[str, Any]:
    data: dict[str, Any] = response.json()
    return data


def assert_problem(response: Response, status_code: int, code: str) -> dict[str, Any]:
    """Assert an RFC 9457 problem response with the given status and error code."""
    assert response.status_code == status_code, response.text
    assert response.headers["content-type"] == PROBLEM_JSON
    body = json_of(response)
    assert body["status"] == status_code
    assert body["code"] == code
    assert body["detail"]
    return body


async def create_user(client: AsyncClient, name: str = "Alice") -> dict[str, Any]:
    response = await client.post("/users", json={"name": name})
    assert response.status_code == 201, response.text
    return json_of(response)


async def create_product(
    client: AsyncClient,
    *,
    name: str = "Product",
    price: str = "10.00",
    stock: int = 10,
    description: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": name, "price": price, "stock": stock}
    if description is not None:
        payload["description"] = description
    response = await client.post("/products", json=payload)
    assert response.status_code == 201, response.text
    return json_of(response)


async def add_to_cart(
    client: AsyncClient, user_id: int, product_id: int, quantity: int = 1
) -> Response:
    return await client.post(
        "/cart/items",
        json={"product_id": product_id, "quantity": quantity},
        headers=as_user(user_id),
    )


async def get_cart(client: AsyncClient, user_id: int) -> dict[str, Any]:
    response = await client.get("/cart", headers=as_user(user_id))
    assert response.status_code == 200, response.text
    return json_of(response)


async def get_product(client: AsyncClient, product_id: int) -> dict[str, Any]:
    response = await client.get(f"/products/{product_id}")
    assert response.status_code == 200, response.text
    return json_of(response)


async def checkout(client: AsyncClient, user_id: int) -> Response:
    return await client.post("/orders", headers=as_user(user_id))


async def fill_cart(
    engine: AsyncEngine, user_id: int, *, lines: int, quantity: int = 1, price: str = "1.00"
) -> list[int]:
    """Create `lines` products (each with stock for a full cart line), put each into the user's
    cart and return their ids.

    Bulk setup goes through SQL: hundreds of API calls would only slow the suite down.
    """
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                "WITH created AS ("
                "  INSERT INTO products (name, price, stock)"
                "  SELECT 'Bulk product ' || n, CAST(:price AS NUMERIC), :stock"
                "  FROM generate_series(1, :lines) AS n"
                "  RETURNING id"
                ") "
                "INSERT INTO cart_items (user_id, product_id, quantity) "
                "SELECT :user_id, id, :quantity FROM created "
                "RETURNING product_id"
            ),
            {
                "price": price,
                "stock": MAX_ITEM_QUANTITY,
                "lines": lines,
                "user_id": user_id,
                "quantity": quantity,
            },
        )
        return sorted(result.scalars())
