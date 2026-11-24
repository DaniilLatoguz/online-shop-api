"""Load demo data (two users and a few products) into an empty database.

Usage: `python -m app.scripts.seed` (docker compose runs it right after the migrations).
The script is idempotent: if any user or product exists, it does nothing.
"""

import asyncio
import logging
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import engine, session_factory
from app.models import Product, User

logger = logging.getLogger("app.seed")

DEMO_USERS = ("Alice", "Bob")

# name, description, price, stock
DEMO_PRODUCTS = (
    ("Mechanical keyboard", "Hot-swappable switches, aluminium case", "129.99", 25),
    ("Wireless mouse", "Ergonomic, 2.4 GHz and Bluetooth", "39.90", 50),
    ('27" 4K monitor', "IPS panel, USB-C power delivery", "349.00", 8),
    ("USB-C hub", "7-in-1: HDMI, USB-A, SD card reader", "45.50", 3),
    ("Noise-cancelling headphones", "Over-ear, 30 h battery life", "199.00", 12),
    ("Laptop stand", "Aluminium, adjustable height", "34.99", 40),
    ("HD webcam", "1080p, built-in microphone", "59.00", 0),
    ("Desk lamp", "LED, adjustable colour temperature", "24.90", 15),
)


async def seed(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Insert the demo data if the database is empty. Returns True if data was inserted."""
    async with sessions() as session:
        users = await session.scalar(select(func.count()).select_from(User))
        products = await session.scalar(select(func.count()).select_from(Product))
        if users or products:
            return False

        session.add_all([User(name=name) for name in DEMO_USERS])
        session.add_all(
            [
                Product(name=name, description=description, price=Decimal(price), stock=stock)
                for name, description, price, stock in DEMO_PRODUCTS
            ]
        )
        await session.commit()
        return True


async def main() -> None:
    configure_logging(get_settings().log_level)
    try:
        if await seed(session_factory):
            logger.info(
                "Demo data loaded: %d users, %d products.", len(DEMO_USERS), len(DEMO_PRODUCTS)
            )
        else:
            logger.info("The database already contains data, demo data is not loaded.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
