from collections.abc import Mapping
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import MONEY_PRECISION, MONEY_SCALE, NAME_MAX_LENGTH, ORDER_TOTAL_PRECISION
from app.core.exceptions import InvalidOrderStatusTransitionError
from app.db.base import Base
from app.models.mixins import TimestampMixin


class OrderStatus(StrEnum):
    CREATED = "created"
    PAID = "paid"
    CANCELLED = "cancelled"


# The order lifecycle as a small state machine: `paid` and `cancelled` are terminal states.
# (Cancelling a paid order would require a refund flow, which is out of scope.)
ORDER_STATUS_TRANSITIONS: Final[Mapping[OrderStatus, frozenset[OrderStatus]]] = MappingProxyType(
    {
        OrderStatus.CREATED: frozenset({OrderStatus.PAID, OrderStatus.CANCELLED}),
        OrderStatus.PAID: frozenset(),
        OrderStatus.CANCELLED: frozenset(),
    }
)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="total_amount_non_negative"),
        # "My orders, newest first" is the main access path.
        Index("ix_orders_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    # RESTRICT: order history must survive; a user with orders cannot be hard-deleted.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    # VARCHAR + CHECK instead of a native PostgreSQL ENUM: adding a status later is a simple
    # constraint change in a migration, while ALTER TYPE ... ADD VALUE has many restrictions.
    status: Mapped[OrderStatus] = mapped_column(
        Enum(
            OrderStatus,
            name="order_status",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=OrderStatus.CREATED,
        server_default=OrderStatus.CREATED.value,
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(ORDER_TOTAL_PRECISION, MONEY_SCALE))

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="raise",
        order_by="OrderItem.id",
    )

    def can_transition_to(self, target: OrderStatus) -> bool:
        return target in ORDER_STATUS_TRANSITIONS[self.status]

    def transition_to(self, target: OrderStatus) -> None:
        """Change the status, enforcing the allowed transitions."""
        if not self.can_transition_to(target):
            raise InvalidOrderStatusTransitionError(self.id, self.status, target)
        self.status = target


class OrderItem(Base):
    """An order line: a snapshot of the product at checkout time (name and price are copied)."""

    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price > 0", name="unit_price_positive"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    # The unique constraint (order_id, product_id) also serves as the index for order_id lookups.
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    product_name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(MONEY_PRECISION, MONEY_SCALE))
    quantity: Mapped[int]

    order: Mapped[Order] = relationship(back_populates="items", lazy="raise")

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity
