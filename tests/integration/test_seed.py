from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.scripts.seed import DEMO_PRODUCTS, DEMO_USERS, seed
from tests.integration.helpers import json_of


async def test_seed_loads_demo_data_only_into_an_empty_database(
    engine: AsyncEngine, client: AsyncClient
) -> None:
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    assert await seed(sessions) is True
    assert await seed(sessions) is False  # idempotent: the second run does nothing

    products = json_of(await client.get("/products?limit=100"))
    assert products["total"] == len(DEMO_PRODUCTS)
    assert json_of(await client.get("/users/1"))["name"] == DEMO_USERS[0]
    assert json_of(await client.get("/users/2"))["name"] == DEMO_USERS[1]
