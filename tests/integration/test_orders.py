from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.constants import MAX_CART_ITEMS, MAX_ITEM_QUANTITY
from tests.integration.helpers import (
    add_to_cart,
    as_user,
    assert_problem,
    checkout,
    create_product,
    create_user,
    fill_cart,
    get_cart,
    get_product,
    json_of,
)


async def place_order(client: AsyncClient, user_id: int, *lines: tuple[int, int]) -> dict[str, Any]:
    """Put (product_id, quantity) lines into the cart and check out."""
    for product_id, quantity in lines:
        assert (await add_to_cart(client, user_id, product_id, quantity)).status_code in (200, 201)
    response = await checkout(client, user_id)
    assert response.status_code == 201, response.text
    return json_of(response)


# --------------------------------------------------------------------------- checkout


async def test_checkout_with_empty_cart_returns_400(client: AsyncClient) -> None:
    user = await create_user(client)

    response = await checkout(client, user["id"])

    assert_problem(response, 400, "cart_empty")
    assert json_of(await client.get("/orders", headers=as_user(user["id"])))["total"] == 0


async def test_checkout_by_unknown_user_returns_404(client: AsyncClient) -> None:
    response = await checkout(client, user_id=42)

    assert_problem(response, 404, "user_not_found")


async def test_order_keeps_price_and_name_from_checkout_time(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client, name="Keyboard", price="100.00", stock=10)
    order = await place_order(client, user["id"], (product["id"], 2))

    # The catalog changes after the order was placed.
    changes = {"name": "Keyboard v2", "price": "150.00"}
    await client.patch(f"/products/{product['id']}", json=changes)

    stored = json_of(await client.get(f"/orders/{order['id']}", headers=as_user(user["id"])))
    assert stored["total_amount"] == "200.00"
    assert stored["items"] == [
        {
            "product_id": product["id"],
            "product_name": "Keyboard",
            "unit_price": "100.00",
            "quantity": 2,
            "line_total": "200.00",
        }
    ]
    # A new order uses the new price.
    new_order = await place_order(client, user["id"], (product["id"], 1))
    assert new_order["items"][0]["unit_price"] == "150.00"
    assert new_order["total_amount"] == "150.00"


async def test_checkout_fails_atomically_when_stock_is_insufficient(client: AsyncClient) -> None:
    user = await create_user(client)
    available = await create_product(client, name="Available", stock=10)
    scarce = await create_product(client, name="Scarce", stock=5)
    await add_to_cart(client, user["id"], available["id"], quantity=2)
    await add_to_cart(client, user["id"], scarce["id"], quantity=4)
    # Stock decreases after the product was put into the cart (the cart does not reserve it).
    await client.patch(f"/products/{scarce['id']}", json={"stock": 3})

    response = await checkout(client, user["id"])

    body = assert_problem(response, 409, "insufficient_stock")
    assert body["context"]["items"] == [
        {"product_id": scarce["id"], "requested": 4, "available": 3}
    ]
    # Nothing changed: no order, cart intact, stock intact.
    assert json_of(await client.get("/orders", headers=as_user(user["id"])))["total"] == 0
    assert (await get_cart(client, user["id"]))["total_quantity"] == 6
    assert (await get_product(client, available["id"]))["stock"] == 10
    assert (await get_product(client, scarce["id"]))["stock"] == 3


async def test_checkout_reports_all_shortages_at_once(client: AsyncClient) -> None:
    user = await create_user(client)
    first = await create_product(client, name="First", stock=5)
    second = await create_product(client, name="Second", stock=5)
    await add_to_cart(client, user["id"], first["id"], quantity=5)
    await add_to_cart(client, user["id"], second["id"], quantity=5)
    await client.patch(f"/products/{first['id']}", json={"stock": 1})
    await client.patch(f"/products/{second['id']}", json={"stock": 0})

    response = await checkout(client, user["id"])

    body = assert_problem(response, 409, "insufficient_stock")
    assert body["context"]["items"] == [
        {"product_id": first["id"], "requested": 5, "available": 1},
        {"product_id": second["id"], "requested": 5, "available": 0},
    ]


async def test_checkout_of_a_full_cart_at_maximum_prices_fits_the_total(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    # The largest order the limits allow: 100 lines x 1 000 units x the maximum price.
    user = await create_user(client)
    await fill_cart(
        engine, user["id"], lines=MAX_CART_ITEMS, quantity=MAX_ITEM_QUANTITY, price="99999999.99"
    )

    response = await checkout(client, user["id"])

    assert response.status_code == 201, response.text
    assert json_of(response)["total_amount"] == "9999999999000.00"


async def test_checkout_of_an_oversized_cart_returns_409_instead_of_500(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    # 1 001 lines x 1 000 units x 99 999 999.99 would not fit the NUMERIC(16, 2) total. Such a cart
    # cannot be built through the API any more, but may exist in data created before the limit.
    user = await create_user(client)
    await fill_cart(
        engine, user["id"], lines=1_001, quantity=MAX_ITEM_QUANTITY, price="99999999.99"
    )

    response = await checkout(client, user["id"])

    body = assert_problem(response, 409, "cart_items_limit_exceeded")
    assert body["context"] == {"limit": MAX_CART_ITEMS}
    # Nothing happened: no order, the cart is untouched.
    assert json_of(await client.get("/orders", headers=as_user(user["id"])))["total"] == 0
    assert len((await get_cart(client, user["id"]))["items"]) == 1_001


async def test_checkout_empties_only_the_buyers_cart(client: AsyncClient) -> None:
    alice = await create_user(client, "Alice")
    bob = await create_user(client, "Bob")
    product = await create_product(client, stock=10)
    await add_to_cart(client, bob["id"], product["id"], quantity=1)

    await place_order(client, alice["id"], (product["id"], 2))

    assert (await get_cart(client, bob["id"]))["total_quantity"] == 1
    assert (await get_product(client, product["id"]))["stock"] == 8


# --------------------------------------------------------------------------- read


async def test_list_orders_returns_only_own_orders_newest_first(client: AsyncClient) -> None:
    alice = await create_user(client, "Alice")
    bob = await create_user(client, "Bob")
    product = await create_product(client, price="1.00", stock=100)
    first = await place_order(client, alice["id"], (product["id"], 1))
    second = await place_order(client, alice["id"], (product["id"], 2))
    await place_order(client, bob["id"], (product["id"], 3))

    response = await client.get("/orders", headers=as_user(alice["id"]))

    assert response.status_code == 200
    body = json_of(response)
    assert body["total"] == 2
    assert [order["id"] for order in body["items"]] == [second["id"], first["id"]]
    assert body["items"][0] == {
        "id": second["id"],
        "status": "created",
        "total_amount": "2.00",
        "created_at": second["created_at"],
        "updated_at": second["updated_at"],
    }


async def test_list_orders_pagination_and_status_filter(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client, stock=100)
    orders = [await place_order(client, user["id"], (product["id"], 1)) for _ in range(3)]
    await client.post(f"/orders/{orders[0]['id']}/pay", headers=as_user(user["id"]))

    page = json_of(await client.get("/orders?limit=2&offset=0", headers=as_user(user["id"])))
    paid = json_of(await client.get("/orders?status=paid", headers=as_user(user["id"])))
    created = json_of(await client.get("/orders?status=created", headers=as_user(user["id"])))

    assert (len(page["items"]), page["total"]) == (2, 3)
    assert [order["id"] for order in paid["items"]] == [orders[0]["id"]]
    assert created["total"] == 2


@pytest.mark.parametrize("query", ["?status=shipped", "?limit=0", "?offset=-5"])
async def test_list_orders_invalid_query_returns_422(client: AsyncClient, query: str) -> None:
    user = await create_user(client)

    response = await client.get(f"/orders{query}", headers=as_user(user["id"]))

    assert_problem(response, 422, "validation_error")


async def test_list_orders_rejects_unknown_query_parameter(client: AsyncClient) -> None:
    # A typo (`state` instead of `status`) must not silently return orders in every status.
    user = await create_user(client)

    response = await client.get("/orders?state=paid", headers=as_user(user["id"]))

    body = assert_problem(response, 422, "validation_error")
    assert [(error["loc"], error["type"]) for error in body["errors"]] == [
        (["query", "state"], "extra_forbidden")
    ]


async def test_get_order_of_another_user_returns_404(client: AsyncClient) -> None:
    alice = await create_user(client, "Alice")
    bob = await create_user(client, "Bob")
    product = await create_product(client)
    order = await place_order(client, alice["id"], (product["id"], 1))

    response = await client.get(f"/orders/{order['id']}", headers=as_user(bob["id"]))

    assert_problem(response, 404, "order_not_found")


async def test_get_unknown_order_returns_404(client: AsyncClient) -> None:
    user = await create_user(client)

    response = await client.get("/orders/999", headers=as_user(user["id"]))

    assert_problem(response, 404, "order_not_found")


# --------------------------------------------------------------------------- status changes


async def test_pay_order(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client)
    order = await place_order(client, user["id"], (product["id"], 1))

    response = await client.post(f"/orders/{order['id']}/pay", headers=as_user(user["id"]))

    assert response.status_code == 200, response.text
    body = json_of(response)
    assert body["status"] == "paid"
    assert body["items"] == order["items"]
    assert body["updated_at"] >= order["updated_at"]


async def test_cancel_order_returns_items_to_stock(client: AsyncClient) -> None:
    user = await create_user(client)
    first = await create_product(client, name="First", stock=10)
    second = await create_product(client, name="Second", stock=5)
    order = await place_order(client, user["id"], (first["id"], 3), (second["id"], 5))
    assert (await get_product(client, second["id"]))["stock"] == 0

    response = await client.post(f"/orders/{order['id']}/cancel", headers=as_user(user["id"]))

    assert response.status_code == 200, response.text
    assert json_of(response)["status"] == "cancelled"
    assert (await get_product(client, first["id"]))["stock"] == 10
    assert (await get_product(client, second["id"]))["stock"] == 5


@pytest.mark.parametrize(
    ("first_action", "second_action"),
    [
        ("pay", "pay"),
        ("pay", "cancel"),
        ("cancel", "cancel"),
        ("cancel", "pay"),
    ],
)
async def test_invalid_status_transitions_return_409(
    client: AsyncClient, first_action: str, second_action: str
) -> None:
    user = await create_user(client)
    product = await create_product(client, stock=10)
    order = await place_order(client, user["id"], (product["id"], 2))
    await client.post(f"/orders/{order['id']}/{first_action}", headers=as_user(user["id"]))
    stock_before = (await get_product(client, product["id"]))["stock"]

    response = await client.post(
        f"/orders/{order['id']}/{second_action}", headers=as_user(user["id"])
    )

    body = assert_problem(response, 409, "invalid_order_status_transition")
    assert body["context"]["order_id"] == order["id"]
    # A rejected transition has no side effects (e.g. stock is not returned twice).
    assert (await get_product(client, product["id"]))["stock"] == stock_before


@pytest.mark.parametrize("action", ["pay", "cancel"])
async def test_status_change_of_another_users_order_returns_404(
    client: AsyncClient, action: str
) -> None:
    alice = await create_user(client, "Alice")
    bob = await create_user(client, "Bob")
    product = await create_product(client)
    order = await place_order(client, alice["id"], (product["id"], 1))

    response = await client.post(f"/orders/{order['id']}/{action}", headers=as_user(bob["id"]))

    assert_problem(response, 404, "order_not_found")
