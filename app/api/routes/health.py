import asyncio
import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import SessionDep
from app.schemas.health import HealthRead

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# A health check must answer quickly even when the database hangs (orchestrators time out too).
HEALTH_CHECK_TIMEOUT_SECONDS = 2.5


@router.get(
    "/health",
    summary="Health check (API and database)",
    responses={
        503: {
            "model": HealthRead,
            "description": "The database is unavailable or did not answer within 2.5 seconds.",
        }
    },
)
async def health(session: SessionDep, response: Response) -> HealthRead:
    try:
        async with asyncio.timeout(HEALTH_CHECK_TIMEOUT_SECONDS):
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        # Any failure means "unavailable": when PostgreSQL rejects the connection (unknown
        # database, wrong password, server starting up), asyncpg raises its own errors that
        # SQLAlchemy does not wrap; a timeout raises TimeoutError.
        logger.warning("Health check failed, the database is unavailable: %r", exc)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthRead(status="unavailable", database="unavailable")
    return HealthRead(status="ok", database="ok")
