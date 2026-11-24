from typing import Any

import pytest
from httpx import AsyncClient

from tests.integration.helpers import assert_problem, create_product, get_product, json_of

# --------------------------------------------------------------------------- create / get


async def test_create_product(client: AsyncClient) -> None:
    payload = {"name": "Keyboard", "description": "Mechanical", "price": 129.99, "stock": 5}

    response = await client.post("/products", json=payload)

    assert response.status_code == 201, response.text
    body = json_of(response)
    assert body["id"] == 1
    assert body["name"] == "Keyboard"
    assert body["description"] == "Mechanical"
    assert body["price"] == "129.99"  # money is returned as a string
    assert body["stock"] == 5
    assert body["created_at"]
    assert body["updated_at"]
    assert response.headers["location"] == "http://testserver/products/1"


async def test_create_product_defaults_and_money_normalization(client: AsyncClient) -> None:
    response = await client.post("/products", json={"name": "Cable", "price": "10"})

    assert response.status_code == 201, response.text
    body = json_of(response)
    assert body["price"] == "10.00"
    assert body["description"] is None
    assert body["stock"] == 0  # not for sale until stock is set explicitly


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"price": "10.00"}, id="missing-name"),
        pytest.param({"name": "X"}, id="missing-price"),
        pytest.param({"name": "", "price": "1"}, id="empty-name"),
        pytest.param({"name": "X", "price": 0}, id="zero-price"),
        pytest.param({"name": "X", "price": "-5"}, id="negative-price"),
        pytest.param({"name": "X", "price": "abc"}, id="price-not-a-number"),
        pytest.param({"name": "X", "price": "10.999"}, id="more-than-two-decimals"),
        pytest.param({"name": "X", "price": "1000000000"}, id="price-too-large"),
        pytest.param({"name": "X", "price": True}, id="price-boolean"),
        pytest.param({"name": "X", "price": "1", "stock": -1}, id="negative-stock"),
        pytest.param({"name": "X", "price": "1", "stock": 1.5}, id="fractional-stock"),
        pytest.param({"name": "X", "price": "1", "stock": "5"}, id="stock-as-string"),
        pytest.param({"name": "X", "price": "1", "sku": "A-1"}, id="unknown-field"),
    ],
)
async def test_create_product_validation(client: AsyncClient, payload: dict[str, Any]) -> None:
    response = await client.post("/products", json=payload)

    body = assert_problem(response, 422, "validation_error")
    assert body["errors"]


async def test_get_product(client: AsyncClient) -> None:
    product = await create_product(client, name="Mouse", price="39.90", stock=3)

    assert await get_product(client, product["id"]) == product


async def test_get_unknown_product_returns_404(client: AsyncClient) -> None:
    response = await client.get("/products/999")

    body = assert_problem(response, 404, "product_not_found")
    assert body["context"] == {"product_id": 999}


@pytest.mark.parametrize("product_id", ["0", "abc", "99999999999"])
async def test_get_product_with_invalid_id_returns_422(
    client: AsyncClient, product_id: str
) -> None:
    response = await client.get(f"/products/{product_id}")

    assert_problem(response, 422, "validation_error")


# --------------------------------------------------------------------------- partial update


async def test_update_product_changes_only_sent_fields(client: AsyncClient) -> None:
    product = await create_product(
        client, name="Keyboard", price="129.99", stock=5, description="Mechanical"
    )

    response = await client.patch(f"/products/{product['id']}", json={"price": "149.50"})

    assert response.status_code == 200, response.text
    body = json_of(response)
    assert body["price"] == "149.50"
    assert body["name"] == "Keyboard"
    assert body["description"] == "Mechanical"
    assert body["stock"] == 5
    assert body["updated_at"] >= body["created_at"]
    assert await get_product(client, product["id"]) == body


async def test_update_product_can_clear_description(client: AsyncClient) -> None:
    product = await create_product(client, description="To be removed")

    response = await client.patch(f"/products/{product['id']}", json={"description": None})

    assert response.status_code == 200
    assert json_of(response)["description"] is None


async def test_update_product_with_empty_body_is_a_no_op(client: AsyncClient) -> None:
    product = await create_product(client)

    response = await client.patch(f"/products/{product['id']}", json={})

    assert response.status_code == 200
    assert json_of(response) == product


@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        pytest.param({"name": None}, "null_not_allowed", id="null-name"),
        pytest.param({"price": None}, "null_not_allowed", id="null-price"),
        pytest.param({"stock": None}, "null_not_allowed", id="null-stock"),
        pytest.param({"price": 0}, "greater_than", id="zero-price"),
        pytest.param({"stock": -1}, "greater_than_equal", id="negative-stock"),
        pytest.param({"name": "  "}, "string_too_short", id="blank-name"),
        pytest.param({"colour": "red"}, "extra_forbidden", id="unknown-field"),
    ],
)
async def test_update_product_validation(
    client: AsyncClient, payload: dict[str, Any], error_type: str
) -> None:
    product = await create_product(client)

    response = await client.patch(f"/products/{product['id']}", json=payload)

    body = assert_problem(response, 422, "validation_error")
    assert body["errors"][0]["type"] == error_type
    assert await get_product(client, product["id"]) == product  # nothing changed


async def test_update_unknown_product_returns_404(client: AsyncClient) -> None:
    response = await client.patch("/products/999", json={"price": "1.00"})

    assert_problem(response, 404, "product_not_found")


# --------------------------------------------------------------------------- list


@pytest.fixture
async def catalog(client: AsyncClient) -> dict[str, int]:
    """Five products created in this order (ids 1..5); returns name -> id."""
    specs = [
        ("Keyboard", "129.99", 5, "Mechanical, RGB"),
        ("Mouse", "39.90", 0, "Wireless"),
        ("Monitor", "349.00", 2, "27 inch 4K display"),
        ("Cable", "9.99", 100, "USB-C, 100% copper"),
        ("Hub", "39.90", 7, None),
    ]
    ids = {}
    for name, price, stock, description in specs:
        product = await create_product(
            client, name=name, price=price, stock=stock, description=description
        )
        ids[name] = product["id"]
    return ids


async def list_names(client: AsyncClient, query: str = "") -> list[str]:
    response = await client.get(f"/products{query}")
    assert response.status_code == 200, response.text
    return [item["name"] for item in json_of(response)["items"]]


async def test_list_products_newest_first_by_default(
    client: AsyncClient, catalog: dict[str, int]
) -> None:
    response = await client.get("/products")

    assert response.status_code == 200
    body = json_of(response)
    assert [item["name"] for item in body["items"]] == [
        "Hub",
        "Cable",
        "Monitor",
        "Mouse",
        "Keyboard",
    ]
    assert (body["total"], body["limit"], body["offset"]) == (5, 20, 0)


async def test_list_products_pagination(client: AsyncClient, catalog: dict[str, int]) -> None:
    first = json_of(await client.get("/products?limit=2&offset=0"))
    second = json_of(await client.get("/products?limit=2&offset=2"))
    last = json_of(await client.get("/products?limit=2&offset=4"))
    beyond = json_of(await client.get("/products?limit=2&offset=10"))

    assert [item["name"] for item in first["items"]] == ["Hub", "Cable"]
    assert [item["name"] for item in second["items"]] == ["Monitor", "Mouse"]
    assert [item["name"] for item in last["items"]] == ["Keyboard"]
    assert beyond["items"] == []
    assert {page["total"] for page in (first, second, last, beyond)} == {5}


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        # Equal prices (Mouse and Hub: 39.90) are ordered by id - a stable order for paging.
        ("?sort_by=price&sort_order=asc", ["Cable", "Mouse", "Hub", "Keyboard", "Monitor"]),
        ("?sort_by=price&sort_order=desc", ["Monitor", "Keyboard", "Hub", "Mouse", "Cable"]),
        ("?sort_by=name&sort_order=asc", ["Cable", "Hub", "Keyboard", "Monitor", "Mouse"]),
        ("?sort_by=created_at&sort_order=asc", ["Keyboard", "Mouse", "Monitor", "Cable", "Hub"]),
    ],
)
async def test_list_products_sorting(
    client: AsyncClient, catalog: dict[str, int], query: str, expected: list[str]
) -> None:
    assert await list_names(client, query) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("?min_price=39.90&sort_by=price&sort_order=asc", ["Mouse", "Hub", "Keyboard", "Monitor"]),
        ("?max_price=39.90&sort_by=price&sort_order=asc", ["Cable", "Mouse", "Hub"]),
        ("?min_price=10&max_price=200&sort_by=price&sort_order=asc", ["Mouse", "Hub", "Keyboard"]),
        ("?in_stock=true&sort_by=name&sort_order=asc", ["Cable", "Hub", "Keyboard", "Monitor"]),
        ("?in_stock=false", ["Mouse"]),
        ("?search=KEY", ["Keyboard"]),  # case-insensitive, in the name
        ("?search=wireless", ["Mouse"]),  # in the description
        ("?search=%25", ["Cable"]),  # "%" is matched literally, not as a wildcard
        ("?search=_", []),  # "_" too
        ("?search=", ["Hub", "Cable", "Monitor", "Mouse", "Keyboard"]),  # empty: no filter
        ("?search=o&in_stock=true&max_price=200&sort_by=price", ["Keyboard", "Cable"]),
    ],
)
async def test_list_products_filtering(
    client: AsyncClient, catalog: dict[str, int], query: str, expected: list[str]
) -> None:
    assert await list_names(client, query) == expected


async def test_list_products_total_respects_filters(
    client: AsyncClient, catalog: dict[str, int]
) -> None:
    body = json_of(await client.get("/products?in_stock=true&limit=1"))

    assert len(body["items"]) == 1
    assert body["total"] == 4


@pytest.mark.parametrize(
    "query",
    [
        "?limit=0",
        "?limit=101",
        "?offset=-1",
        "?min_price=-1",
        "?min_price=abc",
        "?min_price=100&max_price=10",
        "?sort_by=rating",
        "?sort_order=up",
        "?in_stock=maybe",
    ],
)
async def test_list_products_invalid_query_returns_422(client: AsyncClient, query: str) -> None:
    response = await client.get(f"/products{query}")

    assert_problem(response, 422, "validation_error")


async def test_list_products_rejects_unknown_query_parameter(client: AsyncClient) -> None:
    # A typo (`sortby` instead of `sort_by`) must not silently return an unsorted list.
    response = await client.get("/products?sortby=price")

    body = assert_problem(response, 422, "validation_error")
    assert [(error["loc"], error["type"]) for error in body["errors"]] == [
        (["query", "sortby"], "extra_forbidden")
    ]
