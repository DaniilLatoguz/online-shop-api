"""FastAPI dependencies: DB session, services, the current user and reusable path parameters."""

from typing import Annotated

from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PG_INT_MAX
from app.db.session import get_session
from app.services import ProductService, UserService

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Factories are `async def`: they do no IO, and async dependencies run directly on the event loop
# (sync ones would be dispatched to the threadpool). FastAPI caches dependencies per request, so
# all services of one request share the same session and therefore the same transaction.


async def get_user_service(session: SessionDep) -> UserService:
    return UserService(session)


async def get_product_service(session: SessionDep) -> ProductService:
    return ProductService(session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]

# Ids must fit PostgreSQL INTEGER: a larger value would otherwise reach the database and fail.
UserIdPath = Annotated[int, Path(gt=0, le=PG_INT_MAX, description="User id.")]
ProductIdPath = Annotated[int, Path(gt=0, le=PG_INT_MAX, description="Product id.")]
