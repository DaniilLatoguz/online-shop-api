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
