from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.product import Product


class CartItem(TimestampMixin, Base):
    """One line of a user's cart.

    There is no separate `carts` table: every user has exactly one cart, which is the set of their
    cart lines. The composite primary key (user_id, product_id) guarantees that a product appears
    in a cart at most once, so the API addresses a line by its product id.
    """

    __tablename__ = "cart_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    quantity: Mapped[int]

    # lazy="raise": with AsyncSession an implicit lazy load is an error anyway; this makes a
    # forgotten eager load fail loudly and early instead of deep inside serialization.
    product: Mapped["Product"] = relationship(lazy="raise")

    # The cart shows *current* prices; the price is frozen only when an order is created.
    @property
    def product_name(self) -> str:
        return self.product.name

    @property
    def unit_price(self) -> Decimal:
        return self.product.price

    @property
    def line_total(self) -> Decimal:
        return self.product.price * self.quantity
