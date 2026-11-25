from collections.abc import Iterable, Sequence

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product
from app.schemas.common import SortOrder
from app.schemas.product import ProductListParams, ProductSortField

_SORT_COLUMNS = {
    ProductSortField.CREATED_AT: Product.created_at,
    ProductSortField.PRICE: Product.price,
    ProductSortField.NAME: Product.name,
}


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so that user input is matched literally ("100%" is not a pattern)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _filter_conditions(params: ProductListParams) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if params.search:
        pattern = f"%{_escape_like(params.search)}%"
        conditions.append(
            or_(
                Product.name.ilike(pattern, escape="\\"),
                Product.description.ilike(pattern, escape="\\"),
            )
        )
    if params.min_price is not None:
        conditions.append(Product.price >= params.min_price)
    if params.max_price is not None:
        conditions.append(Product.price <= params.max_price)
    if params.in_stock is True:
        conditions.append(Product.stock > 0)
    elif params.in_stock is False:
        conditions.append(Product.stock == 0)
    return conditions


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, product_id: int) -> Product | None:
        return await self._session.get(Product, product_id)

    def add(self, product: Product) -> None:
        self._session.add(product)

    async def list(self, params: ProductListParams) -> Sequence[Product]:
        sort_column = _SORT_COLUMNS[params.sort_by]
        if params.sort_order is SortOrder.ASC:
            ordering = (sort_column.asc(), Product.id.asc())
        else:
            ordering = (sort_column.desc(), Product.id.desc())
        # `id` is a tie-breaker: offset pagination needs a total, deterministic order, otherwise
        # rows with equal sort keys could repeat or disappear between pages.
        stmt = (
            select(Product)
            .where(*_filter_conditions(params))
            .order_by(*ordering)
            .limit(params.limit)
            .offset(params.offset)
        )
        return (await self._session.scalars(stmt)).all()

    async def count(self, params: ProductListParams) -> int:
        stmt = select(func.count()).select_from(Product).where(*_filter_conditions(params))
        return (await self._session.execute(stmt)).scalar_one()

    async def lock_many(self, product_ids: Iterable[int]) -> dict[int, Product]:
        """`SELECT ... FOR NO KEY UPDATE` the given products, locking rows in ascending id order.

        Every transaction that locks several products does it in the same order, which rules out
        deadlocks between concurrent checkouts and cancellations touching the same products.

        The callers change only `stock`, never the key, so `NO KEY` is enough: the lock still
        serializes all stock changes, but does not block foreign-key checks (`FOR KEY SHARE`),
        e.g. other customers adding the product to their carts while a checkout is running.
        """
        stmt = (
            select(Product)
            .where(Product.id.in_(set(product_ids)))
            .order_by(Product.id)
            .with_for_update(key_share=True)  # FOR NO KEY UPDATE
            # If a product is already in the session, overwrite it with the locked (latest) row.
            .execution_options(populate_existing=True)
        )
        products = (await self._session.scalars(stmt)).all()
        return {product.id: product for product in products}
