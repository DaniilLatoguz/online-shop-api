from typing import Literal

from pydantic import BaseModel


class HealthRead(BaseModel):
    status: Literal["ok", "unavailable"]
    database: Literal["ok", "unavailable"]
