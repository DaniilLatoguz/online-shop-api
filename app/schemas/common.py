"""Building blocks shared by all API schemas (DTOs).

Schemas are deliberately separate from the ORM models: the API contract can evolve independently
of the database, and no column is exposed by accident.
"""

from pydantic import BaseModel, ConfigDict


class RequestSchema(BaseModel):
    """Base for request bodies: unknown fields are rejected, so a typo is not silently ignored."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResponseSchema(BaseModel):
    """Base for response bodies: can be built from ORM objects (`from_attributes`)."""

    model_config = ConfigDict(from_attributes=True)
