"""Small helpers that keep the API tests short and readable."""

from typing import Any

from httpx import AsyncClient, Response

PROBLEM_JSON = "application/problem+json"


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


async def get_product(client: AsyncClient, product_id: int) -> dict[str, Any]:
    response = await client.get(f"/products/{product_id}")
    assert response.status_code == 200, response.text
    return json_of(response)
