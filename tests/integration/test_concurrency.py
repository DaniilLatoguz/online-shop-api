"""Race conditions: concurrent requests run in real, concurrent database transactions.

The requests are fired with asyncio.gather, so their transactions interleave and contend for
row locks exactly as concurrent requests to a running server would.
"""

import asyncio
from collections.abc import Iterable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models import Product
from app.repositories import ProductRepository
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


async def test_two_customers_compete_for_the_last_unit(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = await create_user(client, "Alice")
    bob = await create_user(client, "Bob")
    product = await create_product(client, stock=1)
    await add_to_cart(client, alice["id"], product["id"])
    await add_to_cart(client, bob["id"], product["id"])
    # Each checkout pauses for 50 ms right after reading the products. Without the row lock both
    # checkouts then read "1 in stock" before either writes, so a missing lock fails this test on
    # every run, not only when the event loop happens to interleave the requests that way.
    lock_many = ProductRepository.lock_many

    async def lock_many_then_pause(
        repository: ProductRepository, product_ids: Iterable[int]
    ) -> dict[int, Product]:
        products = await lock_many(repository, product_ids)
        await asyncio.sleep(0.05)
        return products

    monkeypatch.setattr(ProductRepository, "lock_many", lock_many_then_pause)

    responses = await asyncio.gather(checkout(client, alice["id"]), checkout(client, bob["id"]))

    # Exactly one checkout wins; the other sees the updated stock under the row lock.
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert (await get_product(client, product["id"]))["stock"] == 0


async def test_double_submitted_checkout_creates_a_single_order(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client, stock=10)
    await add_to_cart(client, user["id"], product["id"], quantity=2)

    responses = await asyncio.gather(*(checkout(client, user["id"]) for _ in range(5)))

    assert sorted(response.status_code for response in responses) == [201, 400, 400, 400, 400]
    orders = json_of(await client.get("/orders", headers=as_user(user["id"])))
    assert orders["total"] == 1
    assert (await get_product(client, product["id"]))["stock"] == 8  # written off only once


async def test_concurrent_adds_of_the_same_product_are_merged(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client, stock=100)

    responses = await asyncio.gather(
        *(add_to_cart(client, user["id"], product["id"], quantity=1) for _ in range(5))
    )

    # One request created the line, the others incremented it; none failed on the primary key.
    assert sorted(response.status_code for response in responses) == [200, 200, 200, 200, 201]
    cart = await get_cart(client, user["id"])
    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 5


async def test_concurrent_pay_and_cancel_of_one_order(client: AsyncClient) -> None:
    user = await create_user(client)
    product = await create_product(client, stock=5)
    await add_to_cart(client, user["id"], product["id"], quantity=5)
    order = json_of(await checkout(client, user["id"]))

    actions = ["pay", "cancel"] * 4
    responses = await asyncio.gather(
        *(
            client.post(f"/orders/{order['id']}/{action}", headers=as_user(user["id"]))
            for action in actions
        )
    )

    # The order row lock serializes the transitions: exactly one succeeds, the rest get 409.
    assert sorted(response.status_code for response in responses) == [200] + [409] * 7
    final = json_of(await client.get(f"/orders/{order['id']}", headers=as_user(user["id"])))
    expected_stock = 5 if final["status"] == "cancelled" else 0
    assert (await get_product(client, product["id"]))["stock"] == expected_stock


async def test_product_lock_blocks_stock_changes_but_not_foreign_key_checks(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    # Checkout and cancellation lock products FOR NO KEY UPDATE. Adding a product to a cart checks
    # the foreign key with FOR KEY SHARE on the product row: it must not wait for a running
    # checkout (it would with FOR UPDATE), while a stock change still has to wait.
    user = await create_user(client)
    product = await create_product(client, stock=10)

    async with AsyncSession(engine) as session, session.begin():
        await ProductRepository(session).lock_many([product["id"]])  # as a checkout does
        adding = asyncio.create_task(add_to_cart(client, user["id"], product["id"]))
        changing_stock = asyncio.create_task(
            client.patch(f"/products/{product['id']}", json={"stock": 5})
        )
        finished_under_lock, _ = await asyncio.wait({adding, changing_stock}, timeout=1)
    # The lock is released here, so both requests complete.
    added, changed = await asyncio.gather(adding, changing_stock)

    assert finished_under_lock == {adding}
    assert added.status_code == 201
    assert changed.status_code == 200
    assert (await get_product(client, product["id"]))["stock"] == 5
