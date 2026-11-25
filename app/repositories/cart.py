from collections.abc import Iterable, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import CartItem


class CartRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_items(self, user_id: int) -> Sequence[CartItem]:
        """Cart lines together with their products, in the order they were added."""
        stmt = (
            select(CartItem)
            .where(CartItem.user_id == user_id)
            .options(joinedload(CartItem.product, innerjoin=True))
            .order_by(CartItem.created_at, CartItem.product_id)
        )
        return (await self._session.scalars(stmt)).all()

    async def get_item(self, user_id: int, product_id: int) -> CartItem | None:
        """One cart line with its product."""
        stmt = (
            select(CartItem)
            .where(CartItem.user_id == user_id, CartItem.product_id == product_id)
            .options(joinedload(CartItem.product, innerjoin=True))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    def add(self, item: CartItem) -> None:
        self._session.add(item)

    async def count_items(self, user_id: int) -> int:
        """Number of lines (different products) in the user's cart."""
        stmt = select(func.count()).select_from(CartItem).where(CartItem.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one()

    async def delete_item(self, user_id: int, product_id: int) -> bool:
        """Delete one line; return False if the product was not in the cart."""
        stmt = (
            delete(CartItem)
            .where(CartItem.user_id == user_id, CartItem.product_id == product_id)
            .returning(CartItem.product_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def delete_items(self, user_id: int, product_ids: Iterable[int]) -> None:
        stmt = delete(CartItem).where(
            CartItem.user_id == user_id, CartItem.product_id.in_(set(product_ids))
        )
        await self._session.execute(stmt)

    async def clear(self, user_id: int) -> None:
        await self._session.execute(delete(CartItem).where(CartItem.user_id == user_id))
