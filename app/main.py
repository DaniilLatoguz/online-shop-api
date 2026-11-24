from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.errors import register_exception_handlers, use_problem_json_in_openapi
from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import engine

API_DESCRIPTION = """
Backend for a simplified online shop: **products**, **cart** and **orders**.

* **Users.** There is no authentication: cart and order endpoints identify the user by the
  `X-User-Id` header. Create a user with `POST /users` (demo data already contains users 1 and 2).
  A missing or malformed header gives 422, an unknown user gives 404.
* **Money** is accepted as a number or a string and always returned as a string with two decimals
  (`"19.90"`), so that clients never parse it as a binary float.
* **Errors** use the RFC 9457 *problem details* format (`application/problem+json`) with a stable
  machine-readable `code`.
"""

OPENAPI_TAGS = [
    {"name": "users", "description": "Create and read users."},
    {"name": "products", "description": "Product catalog: create, update, search."},
    {"name": "cart", "description": "The current user's cart (`X-User-Id` header)."},
    {"name": "orders", "description": "Checkout and the current user's orders (`X-User-Id`)."},
    {"name": "health", "description": "Service health."},
]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()  # close pooled connections on shutdown


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.include_router(api_router)
    use_problem_json_in_openapi(app)
    return app


app = create_app()
