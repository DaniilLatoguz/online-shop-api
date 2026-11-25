ARG PYTHON_VERSION=3.13

# ----------------------------------------------------------------------------- base
FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# The application never runs as root.
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app \
    && install --directory --owner app --group app /app

WORKDIR /app

# ----------------------------------------------------------------------------- dependencies
FROM base AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN pip install --no-cache-dir uv==0.13.9

# Only the dependency manifests: this layer is rebuilt only when dependencies change.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM builder AS builder-test
RUN uv sync --locked --no-dev --group test --no-install-project

# ----------------------------------------------------------------------------- test image
# Used by `docker compose run --rm tests`.
FROM base AS test

COPY --from=builder-test /opt/venv /opt/venv
COPY --chown=app:app pyproject.toml alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app
COPY --chown=app:app tests ./tests

USER app
CMD ["pytest"]

# ----------------------------------------------------------------------------- runtime image
# The last stage is the default build target.
FROM base AS runtime

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app

USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]