from typing import Annotated

from pydantic import ConfigDict, Field

from app.core.constants import MAX_ITEM_QUANTITY
from app.schemas.common import EntityId, Money, RequestSchema, ResponseSchema

Quantity = Annotated[int, Field(strict=True, ge=1, le=MAX_ITEM_QUANTITY)]


class CartItemCreate(RequestSchema):
    model_config = ConfigDict(json_schema_extra={"examples": [{"product_id": 1, "quantity": 2}]})

    product_id: EntityId
    quantity: Quantity


class CartItemUpdate(RequestSchema):
    model_config = ConfigDict(json_schema_extra={"examples": [{"quantity": 3}]})

    quantity: Quantity


class CartItemRead(ResponseSchema):
    product_id: int
    product_name: str
    unit_price: Money = Field(description="Current price of the product.")
    quantity: int
    line_total: Money = Field(description="unit_price x quantity.")


class CartRead(ResponseSchema):
    items: list[CartItemRead]
    total_quantity: int
    total_amount: Money
