"""Domain errors raised by services and models.

They are deliberately HTTP-agnostic: the mapping "error category -> HTTP status" lives in
`app.api.errors`, so the business layer can be reused outside of the web framework.
"""

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, ClassVar


class AppError(Exception):
    """Base class for expected (business) errors."""

    code: ClassVar[str] = "app_error"

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context


# --------------------------------------------------------------------------- categories


class NotFoundError(AppError):
    """The requested resource does not exist (or is not visible to the current user)."""

    code = "not_found"


class ConflictError(AppError):
    """The request is valid but conflicts with the current state of a resource."""

    code = "conflict"


class BusinessRuleViolationError(AppError):
    """The request breaks a business rule that does not depend on concurrent state."""

    code = "business_rule_violation"


# --------------------------------------------------------------------------- not found


class UserNotFoundError(NotFoundError):
    code = "user_not_found"

    def __init__(self, user_id: int) -> None:
        super().__init__(f"User with id {user_id} was not found.", context={"user_id": user_id})


class ProductNotFoundError(NotFoundError):
    code = "product_not_found"

    def __init__(self, product_id: int) -> None:
        super().__init__(
            f"Product with id {product_id} was not found.", context={"product_id": product_id}
        )


class CartItemNotFoundError(NotFoundError):
    code = "cart_item_not_found"

    def __init__(self, product_id: int) -> None:
        super().__init__(
            f"Product with id {product_id} is not in the cart.", context={"product_id": product_id}
        )


class OrderNotFoundError(NotFoundError):
    code = "order_not_found"

    def __init__(self, order_id: int) -> None:
        super().__init__(f"Order with id {order_id} was not found.", context={"order_id": order_id})


# --------------------------------------------------------------------------- business rules


class EmptyCartError(BusinessRuleViolationError):
    code = "cart_empty"

    def __init__(self) -> None:
        super().__init__("Cannot create an order: the cart is empty.")


@dataclass(frozen=True, slots=True)
class StockShortage:
    product_id: int
    requested: int
    available: int


class InsufficientStockError(ConflictError):
    code = "insufficient_stock"

    def __init__(self, shortages: Sequence[StockShortage]) -> None:
        summary = "; ".join(
            f"product {s.product_id}: requested {s.requested}, available {s.available}"
            for s in shortages
        )
        super().__init__(
            f"Insufficient stock ({summary}).",
            context={"items": [asdict(shortage) for shortage in shortages]},
        )
        self.shortages = tuple(shortages)


class CartItemQuantityLimitError(ConflictError):
    code = "cart_item_quantity_limit_exceeded"

    def __init__(self, product_id: int, requested: int, limit: int) -> None:
        super().__init__(
            f"A cart line cannot contain more than {limit} units "
            f"(product {product_id}: requested {requested}).",
            context={"product_id": product_id, "requested": requested, "limit": limit},
        )


class CartItemsLimitError(ConflictError):
    code = "cart_items_limit_exceeded"

    def __init__(self, limit: int) -> None:
        super().__init__(
            f"A cart cannot contain more than {limit} different products.",
            context={"limit": limit},
        )


class InvalidOrderStatusTransitionError(ConflictError):
    code = "invalid_order_status_transition"

    def __init__(self, order_id: int, current: str, target: str) -> None:
        super().__init__(
            f"Order {order_id} cannot change status from '{current}' to '{target}'.",
            context={"order_id": order_id, "current_status": current, "target_status": target},
        )
