from datetime import datetime
from typing import Annotated

from pydantic import ConfigDict, Field

from app.core.constants import NAME_MAX_LENGTH
from app.schemas.common import RequestSchema, ResponseSchema


class UserCreate(RequestSchema):
    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "Alice"}]})

    name: Annotated[str, Field(min_length=1, max_length=NAME_MAX_LENGTH)]


class UserRead(ResponseSchema):
    id: int
    name: str
    created_at: datetime
