"""Building blocks shared by all API schemas (DTOs).

Schemas are deliberately separate from the ORM models: the API contract can evolve independently
of the database, and no column is exposed by accident.
"""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer

from app.core.constants import MONEY_PRECISION, MONEY_SCALE, PG_INT_MAX
from app.core.money import to_money


class RequestSchema(BaseModel):
    """Base for request bodies: unknown fields are rejected, so a typo is not silently ignored."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResponseSchema(BaseModel):
    """Base for response bodies: can be built from ORM objects (`from_attributes`)."""

    model_config = ConfigDict(from_attributes=True)


def _serialize_money(value: Decimal) -> str:
    return str(to_money(value))


# Money is accepted as a JSON number or string and always returned as a string with two decimals
# ("19.90"): a JSON number would be parsed as a binary float by most clients and lose precision.
Price = Annotated[
    Decimal,
    Field(gt=0, max_digits=MONEY_PRECISION, decimal_places=MONEY_SCALE, examples=["129.99"]),
    AfterValidator(to_money),
]
Money = Annotated[
    Decimal,
    PlainSerializer(_serialize_money, return_type=str, when_used="json"),
    Field(examples=["129.99"]),
]

# Body ids are strict integers: `true`, `"5"` or `5.0` are rejected instead of being coerced.
EntityId = Annotated[int, Field(strict=True, gt=0, le=PG_INT_MAX)]


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class PaginationParams(BaseModel):
    """`limit` / `offset` query parameters; the base of every query-parameter model.

    Unknown query parameters are rejected (422), like unknown body fields: a typo such as
    `?sortby=price` must not silently return an unsorted list.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    limit: int = Field(default=20, ge=1, le=100, description="Maximum number of items to return.")
    offset: int = Field(default=0, ge=0, le=PG_INT_MAX, description="Number of items to skip.")


ItemT = TypeVar("ItemT")


class Page(BaseModel, Generic[ItemT]):
    """A page of results plus what a client needs to render pagination."""

    items: list[ItemT]
    total: int = Field(description="Total number of items matching the query (ignores paging).")
    limit: int
    offset: int
