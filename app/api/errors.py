"""Turning exceptions into HTTP error responses (RFC 9457 problem details) and documenting them."""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError, BusinessRuleViolationError, ConflictError, NotFoundError
from app.schemas.errors import ProblemDetail, ValidationErrorItem

PROBLEM_JSON = "application/problem+json"

# Error category -> HTTP status. This is the only place where domain errors meet HTTP.
_STATUS_BY_CATEGORY: tuple[tuple[type[AppError], int], ...] = (
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (BusinessRuleViolationError, status.HTTP_400_BAD_REQUEST),
)

_RESPONSE_DESCRIPTIONS = {
    400: "Business rule violation, e.g. creating an order from an empty cart.",
    404: "Resource not found (including an unknown user in `X-User-Id`).",
    409: "Conflict with the current state: insufficient stock, cart limits, "
    "invalid order status change.",
    422: "Request validation failed (body, query, path or header).",
}


def status_code_for(error: AppError) -> int:
    for category, status_code in _STATUS_BY_CATEGORY:
        if isinstance(error, category):
            return status_code
    return status.HTTP_400_BAD_REQUEST


def problem_response(
    request: Request,
    status_code: int,
    *,
    code: str,
    detail: str,
    errors: list[ValidationErrorItem] | None = None,
    context: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    problem = ProblemDetail(
        title=HTTPStatus(status_code).phrase,
        status=status_code,
        detail=detail,
        instance=request.url.path,
        code=code,
        errors=errors,
        context=context,
    )
    return JSONResponse(
        problem.model_dump(mode="json", exclude_none=True),
        status_code=status_code,
        media_type=PROBLEM_JSON,
        headers=headers,
    )


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return problem_response(
        request, status_code_for(exc), code=exc.code, detail=exc.message, context=exc.context
    )


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        ValidationErrorItem(loc=list(error["loc"]), msg=error["msg"], type=error["type"])
        for error in exc.errors()
    ]
    return problem_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_error",
        detail="Request validation failed.",
        errors=errors,
    )


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Errors produced by the framework itself: unknown route (404), wrong method (405), ..."""
    try:
        code = HTTPStatus(exc.status_code).name.lower()
    except ValueError:
        code = "http_error"
    return problem_response(
        request, exc.status_code, code=code, detail=str(exc.detail), headers=exc.headers
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # No internals leak to the client. The traceback is still logged by the server: Starlette
    # re-raises the exception after this handler has produced the response.
    return problem_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        detail="An unexpected error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.exception_handler(AppError)(handle_app_error)
    app.exception_handler(RequestValidationError)(handle_validation_error)
    app.exception_handler(StarletteHTTPException)(handle_http_exception)
    app.exception_handler(Exception)(handle_unexpected_error)


def problem_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries for the error statuses an endpoint can return."""
    return {
        code: {"model": ProblemDetail, "description": _RESPONSE_DESCRIPTIONS[code]}
        for code in status_codes
    }


def use_problem_json_in_openapi(app: FastAPI) -> None:
    """Document problem responses with the media type they are really sent with.

    FastAPI documents every response model as `application/json`; error bodies are sent as
    `application/problem+json`, so the generated schema is adjusted once and cached.
    """
    generate_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = generate_openapi()
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                for response in operation.get("responses", {}).values():
                    content = response.get("content", {})
                    json_content = content.get("application/json", {})
                    if json_content.get("schema", {}).get("$ref", "").endswith("/ProblemDetail"):
                        response["content"] = {PROBLEM_JSON: json_content}
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
