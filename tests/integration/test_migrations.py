"""The schema is created only by Alembic migrations, so they are tested like code."""

from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  (registers all tables on Base.metadata)
from app.db.base import Base
from tests.integration.conftest import (
    build_test_database_url,
    drop_database,
    recreate_database,
    run_alembic,
)

APP_TABLES = {"users", "products", "cart_items", "orders", "order_items"}


def _schema_diff(connection: Connection) -> list[Any]:
    context = MigrationContext.configure(connection, opts={"compare_server_default": True})
    return list(compare_metadata(context, Base.metadata))


def _table_names(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names())


async def test_models_and_migrations_are_in_sync(engine: AsyncEngine) -> None:
    """Same check as `alembic check`: autogenerate would find nothing to add."""
    async with engine.connect() as connection:
        assert await connection.run_sync(_schema_diff) == []


async def test_migrations_upgrade_and_downgrade_cleanly() -> None:
    url = build_test_database_url("_test_migrations")
    await recreate_database(url)
    scratch_engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with scratch_engine.begin() as connection:
            await connection.run_sync(run_alembic, "head")
            after_upgrade = await connection.run_sync(_table_names)
            await connection.run_sync(run_alembic, "base", downgrade=True)
            after_downgrade = await connection.run_sync(_table_names)
            await connection.run_sync(run_alembic, "head")
            after_second_upgrade = await connection.run_sync(_table_names)
    finally:
        await scratch_engine.dispose()
        await drop_database(url)

    assert after_upgrade == APP_TABLES | {"alembic_version"}
    assert after_downgrade == {"alembic_version"}
    assert after_second_upgrade == after_upgrade


async def test_0002_marks_existing_order_lines_as_written_off() -> None:
    """Before 0002 every order line was written off the stock; the migration records that."""
    url = build_test_database_url("_test_migration_0002")
    await recreate_database(url)
    scratch_engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with scratch_engine.begin() as connection:
            await connection.run_sync(run_alembic, "0001")
            for statement in (
                "INSERT INTO users (name) VALUES ('Legacy')",
                "INSERT INTO products (name, price, stock) VALUES ('Lamp', 10, 4)",
                "INSERT INTO orders (user_id, total_amount) VALUES (1, 20)",
                "INSERT INTO order_items (order_id, product_id, product_name, unit_price, "
                "quantity) VALUES (1, 1, 'Lamp', 10, 2)",
            ):
                await connection.execute(text(statement))
            await connection.run_sync(run_alembic, "0002")
            row = (
                await connection.execute(
                    text(
                        "SELECT order_items.stock_deducted, products.stock FROM order_items "
                        "JOIN products ON products.id = order_items.product_id"
                    )
                )
            ).one()
    finally:
        await scratch_engine.dispose()
        await drop_database(url)

    assert tuple(row) == (True, 4)  # the flag is set, existing stock values are kept
