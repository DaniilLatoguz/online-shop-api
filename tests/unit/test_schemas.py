"""Validation rules of the API schemas (no database needed)."""

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.cart import CartItemCreate, CartItemRead
from app.schemas.product import ProductCreate, ProductListParams, ProductUpdate


@pytest.mark.parametrize(
    ("raw_price", "expected"),
    [("10", "10.00"), (10, "10.00"), ("19.9", "19.90"), (19.99, "19.99"), ("0.01", "0.01")],
)
def test_price_is_normalized_to_two_decimals(raw_price: object, expected: str) -> None:
    product = ProductCreate.model_validate({"name": "X", "price": raw_price})

    assert str(product.price) == expected


@pytest.mark.parametrize(
    "raw_price",
    [0, "-0.01", "10.001", "100000000", True, "NaN", "Infinity", "ten"],
)
def test_invalid_prices_are_rejected(raw_price: object) -> None:
    with pytest.raises(ValidationError):
        ProductCreate.model_validate({"name": "X", "price": raw_price})


def test_product_name_is_stripped_and_required() -> None:
    assert ProductCreate.model_validate({"name": "  Desk  ", "price": 1}).name == "Desk"
    with pytest.raises(ValidationError):
        ProductCreate.model_validate({"name": "   ", "price": 1})


def test_update_keeps_track_of_sent_fields_only() -> None:
    update = ProductUpdate.model_validate({"price": "5"})

    assert update.model_dump(exclude_unset=True) == {"price": Decimal("5.00")}


@pytest.mark.parametrize("field", ["name", "price", "stock"])
def test_update_rejects_null_for_required_columns(field: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProductUpdate.model_validate({field: None})

    assert exc_info.value.errors()[0]["type"] == "null_not_allowed"


def test_update_allows_clearing_the_description() -> None:
    update = ProductUpdate.model_validate({"description": None})

    assert update.model_dump(exclude_unset=True) == {"description": None}


def test_list_params_reject_inverted_price_range() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProductListParams.model_validate({"min_price": "10", "max_price": "5"})

    assert exc_info.value.errors()[0]["type"] == "price_range"


@pytest.mark.parametrize("quantity", [True, "2", 2.0, 0, -1, 1001])
def test_cart_quantity_must_be_a_positive_integer_within_limit(quantity: Any) -> None:
    with pytest.raises(ValidationError):
        CartItemCreate.model_validate({"product_id": 1, "quantity": quantity})


def test_money_is_serialized_as_string_with_two_decimals() -> None:
    line = CartItemRead(
        product_id=1,
        product_name="X",
        unit_price=Decimal("5"),
        quantity=3,
        line_total=Decimal("15"),
    )

    dumped = line.model_dump(mode="json")

    assert dumped["unit_price"] == "5.00"
    assert dumped["line_total"] == "15.00"
