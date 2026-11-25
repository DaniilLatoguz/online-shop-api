"""The main business scenario end to end: add products to the cart -> place an order."""

from httpx import AsyncClient

from tests.integration.helpers import (
    add_to_cart,
    as_user,
    checkout,
    create_product,
    create_user,
    get_cart,
    get_product,
    json_of,
)


async def test_add_to_cart_and_place_order(client: AsyncClient) -> None:
    # Arrange: a customer and two products in the catalog.
    user = await create_user(client, "Alice")
    keyboard = await create_product(client, name="Keyboard", price="129.99", stock=10)
    mouse = await create_product(client, name="Mouse", price="39.90", stock=5)

    # Add products to the cart (the second request for the keyboard merges into one line).
    assert (await add_to_cart(client, user["id"], keyboard["id"], quantity=1)).status_code == 201
    assert (await add_to_cart(client, user["id"], mouse["id"], quantity=3)).status_code == 201
    assert (await add_to_cart(client, user["id"], keyboard["id"], quantity=1)).status_code == 200

    # The cart shows lines with line totals and the grand total.
    cart = await get_cart(client, user["id"])
    assert cart["items"] == [
        {
            "product_id": keyboard["id"],
            "product_name": "Keyboard",
            "unit_price": "129.99",
            "quantity": 2,
            "line_total": "259.98",
        },
        {
            "product_id": mouse["id"],
            "product_name": "Mouse",
            "unit_price": "39.90",
            "quantity": 3,
            "line_total": "119.70",
        },
    ]
    assert cart["total_quantity"] == 5
    assert cart["total_amount"] == "379.68"

    # Place the order.
    response = await checkout(client, user["id"])

    assert response.status_code == 201, response.text
    order = json_of(response)
    assert response.headers["location"] == f"http://testserver/orders/{order['id']}"
    assert order["status"] == "created"
    assert order["total_amount"] == "379.68"  # calculated automatically
    lines = [(item["product_id"], item["unit_price"], item["quantity"]) for item in order["items"]]
    assert lines == [(keyboard["id"], "129.99", 2), (mouse["id"], "39.90", 3)]

    # The cart has been emptied ...
    cart = await get_cart(client, user["id"])
    assert cart["items"] == []
    assert cart["total_amount"] == "0.00"

    # ... the stock has been written off ...
    assert (await get_product(client, keyboard["id"]))["stock"] == 8
    assert (await get_product(client, mouse["id"]))["stock"] == 2

    # ... and the order is available in the customer's order history.
    history = json_of(await client.get("/orders", headers=as_user(user["id"])))
    assert history["total"] == 1
    assert history["items"][0]["id"] == order["id"]
    stored = json_of(await client.get(f"/orders/{order['id']}", headers=as_user(user["id"])))
    assert stored == order
