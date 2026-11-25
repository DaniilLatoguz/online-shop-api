from collections.abc import Sequence

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Order
from app.schemas.order import OrderListParams


def _filter_conditions(user_id: int, params: OrderListParams) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Order.user_id == user_id]
    if params.status is not None:
        conditions.append(Order.status == params.status)
    return conditions


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, order: Order) -> None:
        self._session.add(order)

    async def get_for_user(self, order_id: int, user_id: int) -> Order | None:
        """An order with its items, only if it belongs to the user.

        Filtering by owner in the query means another user's order is simply "not found":
        the API does not even reveal that such an order id exists.
        """
        stmt = (
            select(Order)
            .where(Order.id == order_id, Order.user_id == user_id)
            .options(selectinload(Order.items))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(self, user_id: int, params: OrderListParams) -> Sequence[Order]:
        stmt = (
            select(Order)
            .where(*_filter_conditions(user_id, params))
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(params.limit)
            .offset(params.offset)
        )
        return (await self._session.scalars(stmt)).all()

    async def count_for_user(self, user_id: int, params: OrderListParams) -> int:
        stmt = select(func.count()).select_from(Order).where(*_filter_conditions(user_id, params))
        return (await self._session.execute(stmt)).scalar_one()
