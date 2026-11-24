"""Validation rules of the API schemas (no database needed)."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

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
