from typing import Any

import pytest
from httpx import AsyncClient

from tests.integration.helpers import assert_problem, create_user, json_of


async def test_create_user(client: AsyncClient) -> None:
    response = await client.post("/users", json={"name": "  Alice  "})

    assert response.status_code == 201, response.text
    body = json_of(response)
    assert body["id"] == 1
    assert body["name"] == "Alice"  # surrounding whitespace is stripped
    assert body["created_at"]
    assert response.headers["location"] == "http://testserver/users/1"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="missing-name"),
        pytest.param({"name": ""}, id="empty-name"),
        pytest.param({"name": "   "}, id="blank-name"),
        pytest.param({"name": "x" * 256}, id="too-long"),
        pytest.param({"name": 123}, id="not-a-string"),
        pytest.param({"name": "Bob", "role": "admin"}, id="unknown-field"),
    ],
)
async def test_create_user_validation(client: AsyncClient, payload: dict[str, Any]) -> None:
    response = await client.post("/users", json=payload)

    body = assert_problem(response, 422, "validation_error")
    assert body["errors"][0]["loc"][0] == "body"


async def test_get_user(client: AsyncClient) -> None:
    user = await create_user(client, "Bob")

    response = await client.get(f"/users/{user['id']}")

    assert response.status_code == 200
    assert json_of(response) == user


async def test_get_unknown_user_returns_404(client: AsyncClient) -> None:
    response = await client.get("/users/42")

    body = assert_problem(response, 404, "user_not_found")
    assert body["context"] == {"user_id": 42}
    assert body["instance"] == "/users/42"


@pytest.mark.parametrize("user_id", ["0", "-1", "abc", "2147483648"])
async def test_get_user_with_invalid_id_returns_422(client: AsyncClient, user_id: str) -> None:
    response = await client.get(f"/users/{user_id}")

    assert_problem(response, 422, "validation_error")
