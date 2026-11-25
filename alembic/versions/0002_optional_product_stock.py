"""Optional stock tracking: products.stock NULL = not tracked, order_items.stock_deducted.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24 01:12:40
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing rows keep their numbers (0 still means "sold out"). The CHECK (stock >= 0)
    # constraint stays as it is: NULL passes a CHECK, so it applies only to tracked stock.
    op.alter_column(
        "products",
        "stock",
        existing_type=sa.Integer(),
        nullable=True,
        server_default=None,
        existing_server_default=sa.text("0"),
    )

    # Before this revision every order line was written off the stock, so existing rows get
    # true. The default only fills those rows: new lines always set the value explicitly.
    op.add_column(
        "order_items",
        sa.Column("stock_deducted", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("order_items", "stock_deducted", server_default=None)


def downgrade() -> None:
    op.drop_column("order_items", "stock_deducted")

    # The old schema cannot express "not tracked": such products become "0 in stock".
    op.execute(sa.text("UPDATE products SET stock = 0 WHERE stock IS NULL"))
    op.alter_column(
        "products",
        "stock",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
    )