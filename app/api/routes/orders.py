from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status

from app.api.deps import CurrentUserDep, OrderIdPath, OrderServiceDep
from app.api.errors import problem_responses
from app.schemas.common import Page
from app.schemas.order import OrderListParams, OrderRead, OrderSummary

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create an order from the cart (checkout)",
    description="Creates an order from all cart lines in one transaction: prices are frozen, "
    "the total is calculated, stock is written off and the cart is emptied. "
    "An empty cart gives 400; not enough stock or more than 100 cart lines gives 409 "
    "and nothing is changed.",
    responses=problem_responses(400, 404, 409, 422),
)
async def create_order(
    user: CurrentUserDep, orders: OrderServiceDep, request: Request, response: Response
) -> OrderRead:
    order = await orders.create_from_cart(user.id)
    response.headers["Location"] = str(request.url_for("get_order", order_id=order.id))
    return OrderRead.model_validate(order)


@router.get("", summary="List my orders (newest first)", responses=problem_responses(404, 422))
async def list_orders(
    params: Annotated[OrderListParams, Query()], user: CurrentUserDep, orders: OrderServiceDep
) -> Page[OrderSummary]:
    items, total = await orders.list(user.id, params)
    return Page[OrderSummary](
        items=[OrderSummary.model_validate(order) for order in items],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


@router.get(
    "/{order_id}",
    summary="Get an order with its items",
    description="Orders of other users are reported as 404, not 403: "
    "the API does not reveal which order ids exist.",
    responses=problem_responses(404, 422),
)
async def get_order(
    order_id: OrderIdPath, user: CurrentUserDep, orders: OrderServiceDep
) -> OrderRead:
    return OrderRead.model_validate(await orders.get(user.id, order_id))


@router.post(
    "/{order_id}/pay",
    summary="Pay an order (created -> paid)",
    responses=problem_responses(404, 409, 422),
)
async def pay_order(
    order_id: OrderIdPath, user: CurrentUserDep, orders: OrderServiceDep
) -> OrderRead:
    return OrderRead.model_validate(await orders.pay(user.id, order_id))


@router.post(
    "/{order_id}/cancel",
    summary="Cancel an order (created -> cancelled), returning items to stock",
    responses=problem_responses(404, 409, 422),
)
async def cancel_order(
    order_id: OrderIdPath, user: CurrentUserDep, orders: OrderServiceDep
) -> OrderRead:
    return OrderRead.model_validate(await orders.cancel(user.id, order_id))
