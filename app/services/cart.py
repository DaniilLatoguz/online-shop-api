from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_CART_ITEMS, MAX_ITEM_QUANTITY
from app.core.exceptions import (
    CartItemNotFoundError,
    CartItemQuantityLimitError,
    CartItemsLimitError,
    InsufficientStockError,
    ProductNotFoundError,
    StockShortage,
)
from app.core.money import ZERO
from app.models import CartItem, Product
from app.repositories import CartRepository, ProductRepository


@dataclass(frozen=True, slots=True)
class Cart:
    """Read model of a user's cart: lines with current prices plus computed totals."""

    items: Sequence[CartItem]

    @property
    def total_quantity(self) -> int:
        return sum(item.quantity for item in self.items)

    @property
    def total_amount(self) -> Decimal:
        return sum((item.line_total for item in self.items), ZERO)


def ensure_quantity_available(product: Product, quantity: int) -> None:
    """A cart line may not exceed the per-line limit or the units currently in stock.

    The cart does not reserve stock: this check gives early feedback, and checkout validates
    the stock again.
    """
    if quantity > MAX_ITEM_QUANTITY:
        raise CartItemQuantityLimitError(product.id, quantity, MAX_ITEM_QUANTITY)
    if quantity > product.stock:
        raise InsufficientStockError([StockShortage(product.id, quantity, product.stock)])


def ensure_cart_items_limit(items_count: int) -> None:
    """A cart may hold at most MAX_CART_ITEMS different products.

    Together with MAX_ITEM_QUANTITY this bounds the order total, so it always fits the money
    column. Adding a new line checks the limit early; checkout checks it again.
    """
    if items_count > MAX_CART_ITEMS:
        raise CartItemsLimitError(MAX_CART_ITEMS)


class CartService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._cart = CartRepository(session)
        self._products = ProductRepository(session)

    async def get_cart(self, user_id: int) -> Cart:
        return Cart(items=await self._cart.list_items(user_id))

    async def add_item(self, user_id: int, product_id: int, quantity: int) -> tuple[Cart, bool]:
        """Add units of a product to the cart (merging with an existing line).

        Returns the updated cart and whether a new cart line was created.
        """
        product = await self._products.get(product_id)
        if product is None:
            raise ProductNotFoundError(product_id)

        # Read, then write. Simple, but two concurrent requests for the same product can both
        # find no line here and both try to insert it.
        item = await self._cart.get_item(user_id, product_id)
        created = item is None
        new_quantity = quantity if item is None else item.quantity + quantity
        if created:
            ensure_cart_items_limit(await self._cart.count_items(user_id) + 1)
        ensure_quantity_available(product, new_quantity)
        if item is None:
            self._cart.add(CartItem(user_id=user_id, product_id=product_id, quantity=quantity))
        else:
            item.quantity = new_quantity
        await self._session.commit()
        return await self.get_cart(user_id), created

    async def update_item(self, user_id: int, product_id: int, quantity: int) -> Cart:
        """Set the quantity of a product that is already in the cart."""
        item = await self._cart.get_item(user_id, product_id)
        if item is None:
            raise CartItemNotFoundError(product_id)
        ensure_quantity_available(item.product, quantity)
        item.quantity = quantity
        await self._session.commit()
        return await self.get_cart(user_id)

    async def remove_item(self, user_id: int, product_id: int) -> None:
        if not await self._cart.delete_item(user_id, product_id):
            raise CartItemNotFoundError(product_id)
        await self._session.commit()

    async def clear(self, user_id: int) -> None:
        await self._cart.clear(user_id)
        await self._session.commit()
