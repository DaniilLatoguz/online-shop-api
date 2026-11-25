from collections.abc import Iterable, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
            # `add_quantity` writes through a Core statement that bypasses the identity map,
            # so lines already loaded in this session must be refreshed from the database.
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(stmt)).all()

    async def lock_item(self, user_id: int, product_id: int) -> CartItem | None:
        """`SELECT ... FOR UPDATE` one cart line (with its product, which is not locked)."""
        stmt = (
            select(CartItem)
            .where(CartItem.user_id == user_id, CartItem.product_id == product_id)
            .options(joinedload(CartItem.product, innerjoin=True))
            .with_for_update(of=CartItem)  # FOR UPDATE OF cart_items: the product row stays free
            .execution_options(populate_existing=True)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add_quantity(self, user_id: int, product_id: int, quantity: int) -> int:
        """Add units of a product to the cart atomically and return the resulting quantity.

        `INSERT ... ON CONFLICT DO UPDATE` has no read-then-write race: when two requests add the
        same product at the same time, one inserts the line and the other increments it.
        """
        insert_stmt = pg_insert(CartItem).values(
            user_id=user_id, product_id=product_id, quantity=quantity
        )
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[CartItem.user_id, CartItem.product_id],
            set_={
                "quantity": CartItem.quantity + insert_stmt.excluded.quantity,
                "updated_at": func.now(),
            },
        ).returning(CartItem.quantity)
        return (await self._session.execute(stmt)).scalar_one()

    async def count_items(self, user_id: int) -> int:
        """Number of lines (different products) in the user's cart."""
        stmt = select(func.count()).select_from(CartItem).where(CartItem.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one()

    async def lock_items(self, user_id: int) -> Sequence[CartItem]:
        """`SELECT ... FOR UPDATE` every line of the user's cart (used by checkout)."""
        stmt = (
            select(CartItem)
            .where(CartItem.user_id == user_id)
            .order_by(CartItem.product_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(stmt)).all()

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
