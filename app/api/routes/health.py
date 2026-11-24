from fastapi import APIRouter

from app.schemas.health import HealthRead

router = APIRouter(tags=["health"])


@router.get("/health", summary="Health check")
async def health() -> HealthRead:
    return HealthRead(status="ok")
