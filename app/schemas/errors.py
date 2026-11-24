from typing import Any

from pydantic import BaseModel, Field


class ValidationErrorItem(BaseModel):
    loc: list[str | int] = Field(examples=[["body", "price"]])
    msg: str = Field(examples=["Input should be greater than 0"])
    type: str = Field(examples=["greater_than"])


class ProblemDetail(BaseModel):
    """Error body in the RFC 9457 "Problem Details for HTTP APIs" format.

    Served as `application/problem+json`. On top of the standard members it has `code` (a stable,
    machine-readable error identifier), `errors` (validation errors) and `context` (error data).
    """

    type: str = Field(default="about:blank", description="Problem type URI.")
    title: str = Field(description="HTTP status phrase.", examples=["Not Found"])
    status: int = Field(examples=[404])
    detail: str = Field(examples=["Product with id 42 was not found."])
    instance: str | None = Field(default=None, examples=["/products/42"])
    code: str = Field(examples=["product_not_found"])
    errors: list[ValidationErrorItem] | None = None
    context: dict[str, Any] | None = Field(default=None, examples=[{"product_id": 42}])
