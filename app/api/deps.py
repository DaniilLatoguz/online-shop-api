"""FastAPI dependencies: DB session, services, the current user and reusable path parameters."""

from typing import Annotated

from fastapi import Depends, Header, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PG_INT_MAX
from app.db.session import get_session
from app.models import User
from app.services import CartService, OrderService, ProductService, UserService

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Factories are `async def`: they do no IO, and async dependencies run directly on the event loop
# (sync ones would be dispatched to the threadpool). FastAPI caches dependencies per request, so
# all services of one request share the same session and therefore the same transaction.


async def get_user_service(session: SessionDep) -> UserService:
    return UserService(session)


async def get_product_service(session: SessionDep) -> ProductService:
    return ProductService(session)


async def get_cart_service(session: SessionDep) -> CartService:
    return CartService(session)


async def get_order_service(session: SessionDep) -> OrderService:
    return OrderService(session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]
CartServiceDep = Annotated[CartService, Depends(get_cart_service)]
OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]


async def get_current_user(
    user_id: Annotated[
        int,
        Header(
            alias="X-User-Id",
            gt=0,
            le=PG_INT_MAX,
            description="Id of the user making the request (stands in for authentication).",
        ),
    ],
    users: UserServiceDep,
) -> User:
    """Resolve the current user from the `X-User-Id` header.

    Missing or malformed header -> 422 (request validation); unknown user -> 404.
    """
    return await users.get(user_id)


CurrentUserDep = Annotated[User, Depends(get_current_user)]

# Ids must fit PostgreSQL INTEGER: a larger value would otherwise reach the database and fail.
UserIdPath = Annotated[int, Path(gt=0, le=PG_INT_MAX, description="User id.")]
ProductIdPath = Annotated[int, Path(gt=0, le=PG_INT_MAX, description="Product id.")]
OrderIdPath = Annotated[int, Path(gt=0, le=PG_INT_MAX, description="Order id.")]
