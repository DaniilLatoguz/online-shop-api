from decimal import Decimal

from sqlalchemy import CheckConstraint, Identity, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import MONEY_PRECISION, MONEY_SCALE, NAME_MAX_LENGTH
from app.db.base import Base
from app.models.mixins import TimestampMixin


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        # The API validates these too; the constraints are the last line of defence.
        CheckConstraint("price > 0", name="price_positive"),
        CheckConstraint("stock >= 0", name="stock_non_negative"),
        # Support filtering and sorting of the product list.
        Index("ix_products_created_at", "created_at"),
        Index("ix_products_price", "price"),
        Index("ix_products_name", "name"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(MONEY_PRECISION, MONEY_SCALE))
    stock: Mapped[int] = mapped_column(server_default=text("0"))
