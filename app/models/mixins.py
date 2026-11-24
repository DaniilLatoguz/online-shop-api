from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """`created_at` / `updated_at` maintained by the database clock (TIMESTAMPTZ, UTC)."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Fetch server-generated values (timestamps) with RETURNING right after INSERT/UPDATE.
    # Without it they would be expired, and an async session cannot lazily reload them.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
