from datetime import datetime

from pydantic import Field

from app.models.order import OrderStatus
from app.schemas.common import Money, PaginationParams, ResponseSchema


class OrderItemRead(ResponseSchema):
    product_id: int
    product_name: str = Field(description="Product name at the moment of checkout.")
    unit_price: Money = Field(description="Product price at the moment of checkout.")
    quantity: int
    line_total: Money


class OrderSummary(ResponseSchema):
    id: int
    status: OrderStatus
    total_amount: Money
    created_at: datetime
    updated_at: datetime


class OrderRead(OrderSummary):
    items: list[OrderItemRead]


class OrderListParams(PaginationParams):
    status: OrderStatus | None = Field(
        default=None, description="Return only orders in this status."
    )
