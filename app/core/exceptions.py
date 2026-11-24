"""Domain errors raised by services and models.

They are deliberately HTTP-agnostic: the mapping "error category -> HTTP status" lives in
`app.api.errors`, so the business layer can be reused outside of the web framework.
"""

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


# --------------------------------------------------------------------------- business rules


class InvalidOrderStatusTransitionError(ConflictError):
    code = "invalid_order_status_transition"

    def __init__(self, order_id: int, current: str, target: str) -> None:
        super().__init__(
            f"Order {order_id} cannot change status from '{current}' to '{target}'.",
            context={"order_id": order_id, "current_status": current, "target_status": target},
        )
