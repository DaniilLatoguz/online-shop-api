import logging
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    EmptyCartError,
    InsufficientStockError,
    OrderNotFoundError,
    StockShortage,
)
from app.core.money import ZERO
from app.models import Order, OrderItem, OrderStatus
from app.repositories import CartRepository, OrderRepository, ProductRepository
from app.schemas.order import OrderListParams
from app.services.cart import ensure_cart_items_limit

logger = logging.getLogger(__name__)


class OrderService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._orders = OrderRepository(session)
        self._cart = CartRepository(session)
        self._products = ProductRepository(session)

    async def create_from_cart(self, user_id: int) -> Order:
        """Checkout: turn the user's cart into an order within a single transaction.

        Either everything happens (order created, stock written off, cart emptied) or nothing.
        """
        # 1. Read the cart lines.
        cart_items = await self._cart.list_items(user_id)
        if not cart_items:
            raise EmptyCartError()
        # The line limit keeps the order total within NUMERIC(16, 2).
        ensure_cart_items_limit(len(cart_items))

        # 2. Re-validate stock: the cart does not reserve stock, so it may have changed since the
        #    items were added. All shortages are reported at once.
        products = await self._products.get_many(item.product_id for item in cart_items)
        shortages = [
            StockShortage(item.product_id, item.quantity, products[item.product_id].stock)
            for item in cart_items
            if item.quantity > products[item.product_id].stock
        ]
        if shortages:
            raise InsufficientStockError(shortages)

        # 3. Write off stock and copy the *current* name and price into the order lines, so later
        #    catalog changes never alter an existing order.
        order_items: list[OrderItem] = []
        for cart_item in cart_items:
            product = products[cart_item.product_id]
            product.stock -= cart_item.quantity
            order_items.append(
                OrderItem(
                    product_id=product.id,
                    product_name=product.name,
                    unit_price=product.price,
                    quantity=cart_item.quantity,
                )
            )
        order = Order(
            user_id=user_id,
            status=OrderStatus.CREATED,
            items=order_items,
            total_amount=sum((item.line_total for item in order_items), ZERO),
        )
        self._orders.add(order)

        # 4. Empty the cart: delete exactly the lines that were ordered.
        await self._cart.delete_items(user_id, products.keys())

        await self._session.commit()
        logger.info(
            "Order %s created for user %s (total %s)", order.id, user_id, order.total_amount
        )
        return order

    async def get(self, user_id: int, order_id: int) -> Order:
        order = await self._orders.get_for_user(order_id, user_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        return order

    async def list(self, user_id: int, params: OrderListParams) -> tuple[Sequence[Order], int]:
        orders = await self._orders.list_for_user(user_id, params)
        total = await self._orders.count_for_user(user_id, params)
        return orders, total

    async def pay(self, user_id: int, order_id: int) -> Order:
        """Mark an order as paid (stands in for a confirmation from a payment provider)."""
        order = await self.get(user_id, order_id)
        order.transition_to(OrderStatus.PAID)
        await self._session.commit()
        logger.info("Order %s paid", order.id)
        return order

    async def cancel(self, user_id: int, order_id: int) -> Order:
        """Cancel an unpaid order and return its units to stock."""
        order = await self.get(user_id, order_id)
        order.transition_to(OrderStatus.CANCELLED)
        products = await self._products.get_many(item.product_id for item in order.items)
        for item in order.items:
            products[item.product_id].stock += item.quantity
        await self._session.commit()
        logger.info("Order %s cancelled, stock restored", order.id)
        return order
