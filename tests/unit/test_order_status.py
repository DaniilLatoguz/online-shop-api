from decimal import Decimal

import pytest

from app.core.exceptions import InvalidOrderStatusTransitionError
from app.models import ORDER_STATUS_TRANSITIONS, Order, OrderStatus

CREATED, PAID, CANCELLED = OrderStatus.CREATED, OrderStatus.PAID, OrderStatus.CANCELLED


def make_order(status: OrderStatus) -> Order:
    return Order(id=7, user_id=1, status=status, total_amount=Decimal("10.00"))


@pytest.mark.parametrize(("current", "target"), [(CREATED, PAID), (CREATED, CANCELLED)])
def test_allowed_transitions(current: OrderStatus, target: OrderStatus) -> None:
    order = make_order(current)

    order.transition_to(target)

    assert order.status is target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (CREATED, CREATED),
        (PAID, PAID),
        (PAID, CREATED),
        (PAID, CANCELLED),  # would need a refund flow
        (CANCELLED, CANCELLED),
        (CANCELLED, CREATED),
        (CANCELLED, PAID),
    ],
)
def test_forbidden_transitions(current: OrderStatus, target: OrderStatus) -> None:
    order = make_order(current)

    with pytest.raises(InvalidOrderStatusTransitionError) as exc_info:
        order.transition_to(target)

    assert order.status is current  # unchanged
    assert exc_info.value.context == {
        "order_id": 7,
        "current_status": current,
        "target_status": target,
    }


def test_transition_rules_cover_every_status() -> None:
    assert set(ORDER_STATUS_TRANSITIONS) == set(OrderStatus)
    assert ORDER_STATUS_TRANSITIONS[PAID] == frozenset()
    assert ORDER_STATUS_TRANSITIONS[CANCELLED] == frozenset()
