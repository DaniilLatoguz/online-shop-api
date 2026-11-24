from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_settings = get_settings()

# The engine owns the connection pool; it does not connect until the first query.
engine = create_async_engine(
    _settings.database_url,
    echo=_settings.db_echo,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_pre_ping=True,
)

# expire_on_commit=False: objects stay readable after commit. With an async session an expired
# attribute cannot be lazily refreshed (no implicit IO), so serialization would fail otherwise.
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session (one transaction) per request.

    The session never commits here. Services commit explicitly when a use case succeeds, because
    FastAPI runs the code after `yield` only once the response has been sent: an error during a
    commit placed here could no longer change the response. Closing the session rolls back
    whatever was not committed, e.g. when a service raised a domain error halfway through.
    """
    async with session_factory() as session:
        yield session
