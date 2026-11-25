from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.constants import MAX_CART_ITEMS, MAX_ITEM_QUANTITY
from tests.integration.helpers import (
    add_to_cart,
    as_user,
    assert_problem,
    create_product,
    create_user,
    fill_cart,
    get_cart,
    json_of,
)

# --------------------------------------------------------------------------- user identification


@pytest.mark.parametrize(
    ("headers", "expected_type"),
    [
        pytest.param({}, "missing", id="missing-header"),
        pytest.param({"X-User-Id": "abc"}, "int_parsing", id="not-a-number"),
        pytest.param({"X-User-Id": "0"}, "greater_than", id="zero"),
    ],
)
async def test_invalid_user_header_returns_422(
    client: AsyncClient, headers: dict[str, str], expected_type: str
) -> None:
    response = await client.get("/cart", headers=headers)

    body = assert_problem(response, 422, "validation_error")
    assert [(error["loc"], error["type"]) for error in body["errors"]] == [
        (["header", "X-User-Id"], expected_type)
    ]


async def test_unknown_user_returns_404(client: AsyncClient) -> None:
    response = await client.get("/cart", headers=as_user(42))

    body = assert_problem(response, 404, "user_not_found")
    assert body["context"] == {"user_id": 42}


async def test_header_name_is_case_insensitive(client: AsyncClient) -> None:
    user = await create_user(client)

    response = await client.get("/cart", headers={"x-user-id": str(user["id"])})

    assert response.status_code == 200


# --------------------------------------------------------------------------- view / add


async def test_new_user_has_empty_cart(client: AsyncClient) -> None:
    user = await create_user(client)

    cart = await get_cart(client, user["id"])

    assert cart == {"items": [], "total_quantity": 0, "total_amount": "0.00"}


async def test_add_product_creates_cart_line(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client, name="Mouse", price="39.90", stock=10)

    response = await add_to_cart(client, user["id"], product["id"], quantity=2)

    assert response.status_code == 201, response.text
    assert "location" not in response.headers  # the body is the whole cart, see docs/decisions.md
    assert json_of(response) == {
        "items": [
            {
                "product_id": product["id"],
                "product_name": "Mouse",
                "unit_price": "39.90",
                "quantity": 2,
                "line_total": "79.80",
            }
        ],
        "total_quantity": 2,
        "total_amount": "79.80",
    }


async def test_adding_same_product_again_increases_quantity(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client, price="5.00", stock=10)
    await add_to_cart(client, user["id"], product["id"], quantity=2)

    response = await add_to_cart(client, user["id"], product["id"], quantity=3)

    assert response.status_code == 200, response.text  # existing line updated, nothing created
    cart = json_of(response)
    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 5
    assert cart["total_amount"] == "25.00"


async def test_cart_total_sums_all_lines(client: AsyncClient) -> None:
    user = await create_user(client)
    first = await create_product(client, name="A", price="0.10", stock=10)
    second = await create_product(client, name="B", price="0.20", stock=10)
    await add_to_cart(client, user["id"], first["id"], quantity=1)
    await add_to_cart(client, user["id"], second["id"], quantity=1)

    cart = await get_cart(client, user["id"])

    # Decimal arithmetic: 0.10 + 0.20 is exactly 0.30 (with floats it would be 0.30000000000000004).
    assert cart["total_amount"] == "0.30"
    assert [item["product_name"] for item in cart["items"]] == ["A", "B"]  # insertion order


async def test_add_unknown_product_returns_404(client: AsyncClient) -> None:
    user = await create_user(client)

    response = await add_to_cart(client, user["id"], product_id=999)

    assert_problem(response, 404, "product_not_found")


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"product_id": 1}, id="missing-quantity"),
        pytest.param({"quantity": 1}, id="missing-product"),
        pytest.param({"product_id": 1, "quantity": 0}, id="zero-quantity"),
        pytest.param({"product_id": 1, "quantity": -2}, id="negative-quantity"),
        pytest.param({"product_id": 1, "quantity": 1.5}, id="fractional-quantity"),
        pytest.param({"product_id": 1, "quantity": "2"}, id="quantity-as-string"),
        pytest.param({"product_id": 1, "quantity": True}, id="quantity-boolean"),
        pytest.param({"product_id": 1, "quantity": MAX_ITEM_QUANTITY + 1}, id="over-limit"),
        pytest.param({"product_id": 0, "quantity": 1}, id="zero-product-id"),
        pytest.param({"product_id": 1, "quantity": 1, "price": "0.01"}, id="unknown-field"),
    ],
)
async def test_add_to_cart_validation(client: AsyncClient, payload: dict[str, Any]) -> None:
    user = await create_user(client)
    await create_product(client)

    response = await client.post("/cart/items", json=payload, headers=as_user(user["id"]))

    assert_problem(response, 422, "validation_error")


# --------------------------------------------------------------------------- stock checks


async def test_add_more_than_stock_returns_409(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client, stock=3)

    response = await add_to_cart(client, user["id"], product["id"], quantity=4)

    body = assert_problem(response, 409, "insufficient_stock")
    assert body["context"] == {
        "items": [{"product_id": product["id"], "requested": 4, "available": 3}]
    }
    assert (await get_cart(client, user["id"]))["items"] == []


async def test_out_of_stock_product_cannot_be_added(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client, stock=0)

    response = await add_to_cart(client, user["id"], product["id"])

    assert_problem(response, 409, "insufficient_stock")


async def test_merged_quantity_is_checked_against_stock_and_rolled_back(
    client: AsyncClient,
) -> None:
    user = await create_user(client)
    product = await create_product(client, stock=5)
    await add_to_cart(client, user["id"], product["id"], quantity=3)

    response = await add_to_cart(client, user["id"], product["id"], quantity=3)

    body = assert_problem(response, 409, "insufficient_stock")
    assert body["context"]["items"] == [
        {"product_id": product["id"], "requested": 6, "available": 5}
    ]
    # The failed request did not change the cart.
    assert (await get_cart(client, user["id"]))["items"][0]["quantity"] == 3


async def test_merged_quantity_cannot_exceed_line_limit(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client, stock=MAX_ITEM_QUANTITY * 2)
    await add_to_cart(client, user["id"], product["id"], quantity=MAX_ITEM_QUANTITY)

    response = await add_to_cart(client, user["id"], product["id"], quantity=1)

    body = assert_problem(response, 409, "cart_item_quantity_limit_exceeded")
    assert body["context"]["limit"] == MAX_ITEM_QUANTITY
    assert (await get_cart(client, user["id"]))["items"][0]["quantity"] == MAX_ITEM_QUANTITY


async def test_untracked_stock_is_not_checked_but_line_limit_applies(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client, stock=None)

    first = await add_to_cart(client, user["id"], product["id"], quantity=MAX_ITEM_QUANTITY)
    over_limit = await add_to_cart(client, user["id"], product["id"], quantity=1)
    changed = await client.patch(
        f"/cart/items/{product['id']}", json={"quantity": 500}, headers=as_user(user["id"])
    )

    assert first.status_code == 201
    assert_problem(over_limit, 409, "cart_item_quantity_limit_exceeded")
    assert changed.status_code == 200
    assert json_of(changed)["items"][0]["quantity"] == 500


# --------------------------------------------------------------------------- cart size limit


async def test_cart_cannot_hold_more_than_the_line_limit(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    user = await create_user(client)
    await fill_cart(engine, user["id"], lines=MAX_CART_ITEMS)
    product = await create_product(client)

    response = await add_to_cart(client, user["id"], product["id"])

    body = assert_problem(response, 409, "cart_items_limit_exceeded")
    assert body["context"] == {"limit": MAX_CART_ITEMS}
    # The rejected line was rolled back.
    cart = await get_cart(client, user["id"])
    assert len(cart["items"]) == MAX_CART_ITEMS
    assert product["id"] not in {item["product_id"] for item in cart["items"]}


async def test_full_cart_still_accepts_more_units_of_its_products(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    user = await create_user(client)
    product_ids = await fill_cart(engine, user["id"], lines=MAX_CART_ITEMS)

    response = await add_to_cart(client, user["id"], product_ids[0], quantity=2)

    assert response.status_code == 200, response.text  # existing line, no new line created
    cart = json_of(response)
    assert len(cart["items"]) == MAX_CART_ITEMS
    assert cart["total_quantity"] == MAX_CART_ITEMS + 2


# --------------------------------------------------------------------------- change quantity


async def test_update_quantity(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client, price="2.50", stock=10)
    await add_to_cart(client, user["id"], product["id"], quantity=1)

    response = await client.patch(
        f"/cart/items/{product['id']}", json={"quantity": 4}, headers=as_user(user["id"])
    )

    assert response.status_code == 200, response.text
    cart = json_of(response)
    assert cart["items"][0]["quantity"] == 4
    assert cart["total_amount"] == "10.00"


async def test_update_quantity_of_product_not_in_cart_returns_404(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client)

    response = await client.patch(
        f"/cart/items/{product['id']}", json={"quantity": 1}, headers=as_user(user["id"])
    )

    assert_problem(response, 404, "cart_item_not_found")


async def test_update_quantity_above_stock_returns_409(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client, stock=2)
    await add_to_cart(client, user["id"], product["id"], quantity=1)

    response = await client.patch(
        f"/cart/items/{product['id']}", json={"quantity": 3}, headers=as_user(user["id"])
    )

    assert_problem(response, 409, "insufficient_stock")
    assert (await get_cart(client, user["id"]))["items"][0]["quantity"] == 1


@pytest.mark.parametrize("quantity", [0, -1, MAX_ITEM_QUANTITY + 1])
async def test_update_quantity_validation(client: AsyncClient, quantity: int) -> None:
    user = await create_user(client)
    product = await create_product(client)
    await add_to_cart(client, user["id"], product["id"])

    response = await client.patch(
        f"/cart/items/{product['id']}", json={"quantity": quantity}, headers=as_user(user["id"])
    )

    assert_problem(response, 422, "validation_error")


# --------------------------------------------------------------------------- remove / clear


async def test_remove_item(client: AsyncClient) -> None:
    user = await create_user(client)
    kept = await create_product(client, name="Kept")
    removed = await create_product(client, name="Removed")
    await add_to_cart(client, user["id"], kept["id"])
    await add_to_cart(client, user["id"], removed["id"])

    response = await client.delete(f"/cart/items/{removed['id']}", headers=as_user(user["id"]))

    assert response.status_code == 204
    assert response.content == b""
    cart = await get_cart(client, user["id"])
    assert [item["product_name"] for item in cart["items"]] == ["Kept"]


async def test_remove_item_not_in_cart_returns_404(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client)

    response = await client.delete(f"/cart/items/{product['id']}", headers=as_user(user["id"]))

    assert_problem(response, 404, "cart_item_not_found")


async def test_clear_cart(client: AsyncClient) -> None:
    user = await create_user(client)
    for name in ("A", "B"):
        product = await create_product(client, name=name)
        await add_to_cart(client, user["id"], product["id"])

    response = await client.delete("/cart", headers=as_user(user["id"]))

    assert response.status_code == 204
    assert (await get_cart(client, user["id"]))["items"] == []


# --------------------------------------------------------------------------- behaviour


async def test_carts_are_isolated_between_users(client: AsyncClient) -> None:
    alice = await create_user(client, "Alice")
    bob = await create_user(client, "Bob")
    product = await create_product(client)
    await add_to_cart(client, alice["id"], product["id"], quantity=2)

    assert (await get_cart(client, bob["id"]))["items"] == []
    assert (await get_cart(client, alice["id"]))["total_quantity"] == 2


async def test_cart_shows_current_product_price(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client, price="10.00")
    await add_to_cart(client, user["id"], product["id"], quantity=2)

    await client.patch(f"/products/{product['id']}", json={"price": "12.00"})

    cart = await get_cart(client, user["id"])
    assert cart["items"][0]["unit_price"] == "12.00"
    assert cart["total_amount"] == "24.00"
