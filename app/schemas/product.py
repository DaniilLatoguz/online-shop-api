from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema
from pydantic_core import PydanticCustomError

from app.core.constants import (
    DESCRIPTION_MAX_LENGTH,
    MONEY_PRECISION,
    MONEY_SCALE,
    NAME_MAX_LENGTH,
    PG_INT_MAX,
)
from app.schemas.common import (
    Money,
    PaginationParams,
    Price,
    RequestSchema,
    ResponseSchema,
    SortOrder,
)

ProductName = Annotated[str, Field(min_length=1, max_length=NAME_MAX_LENGTH)]
ProductDescription = Annotated[str, Field(max_length=DESCRIPTION_MAX_LENGTH)]
Stock = Annotated[
    int,
    Field(
        strict=True,
        ge=0,
        le=PG_INT_MAX,
        description="Units in stock; null means the product does not track stock.",
    ),
]


class ProductCreate(RequestSchema):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Mechanical keyboard",
                    "description": "Hot-swappable switches, aluminium case",
                    "price": "129.99",
                    "stock": 25,
                }
            ]
        }
    )

    name: ProductName
    description: ProductDescription | None = None
    price: Price
    # Omitted or null: stock is not tracked, the product is always available.
    stock: Stock | None = None


class ProductUpdate(RequestSchema):
    """Partial update: only the fields present in the request body are changed."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"price": "119.99", "stock": 40}]})

    # name and price may be omitted but not set to null (see the validator below), so
    # `SkipJsonSchema[None]` keeps null out of their OpenAPI schema; None stays the Python default.
    name: ProductName | SkipJsonSchema[None] = None
    description: ProductDescription | None = None
    price: Price | SkipJsonSchema[None] = None
    stock: Stock | None = None

    @field_validator("name", "price", mode="before")
    @classmethod
    def _reject_explicit_null(cls, value: object) -> object:
        # Omitting a field means "keep it"; sending null for a required column is an error.
        # (Validators do not run for omitted fields, so this only sees values that were sent.)
        # null IS valid for description (clears it) and stock (stops tracking stock).
        if value is None:
            raise PydanticCustomError("null_not_allowed", "Field cannot be null")
        return value


class ProductRead(ResponseSchema):
    id: int
    name: str
    description: str | None
    price: Money
    stock: int | None = Field(description="Units in stock; null - stock is not tracked.")
    created_at: datetime
    updated_at: datetime


class ProductSortField(StrEnum):
    CREATED_AT = "created_at"
    PRICE = "price"
    NAME = "name"


class ProductListParams(PaginationParams):
    """Query parameters of `GET /products`: pagination, filtering and sorting."""

    search: str | None = Field(
        default=None,
        max_length=100,
        description="Case-insensitive substring searched in the name and description "
        "(an empty value means no search).",
    )
    min_price: Decimal | None = Field(
        default=None, ge=0, max_digits=MONEY_PRECISION, decimal_places=MONEY_SCALE
    )
    max_price: Decimal | None = Field(
        default=None, ge=0, max_digits=MONEY_PRECISION, decimal_places=MONEY_SCALE
    )
    in_stock: bool | None = Field(
        default=None,
        description="`true` - available products (stock > 0 or stock not tracked), "
        "`false` - sold-out products (stock = 0).",
    )
    sort_by: ProductSortField = ProductSortField.CREATED_AT
    sort_order: SortOrder = SortOrder.DESC

    @model_validator(mode="after")
    def _check_price_range(self) -> Self:
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise PydanticCustomError(
                "price_range", "min_price must be less than or equal to max_price"
            )
        return self
