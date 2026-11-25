.DEFAULT_GOAL := help
.PHONY: help up down clean logs test test-local lint format typecheck check migrate revision seed

help: ## Show the available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

# ----------------------------------------------------------------------------- Docker
up: ## Build and start PostgreSQL, migrations and the API (http://localhost:8000/docs)
	docker compose up --build

down: ## Stop the containers (the database volume is kept)
	docker compose down

clean: ## Stop the containers and delete the database volume
	docker compose down --volumes

logs: ## Follow the API logs
	docker compose logs -f api

test: ## Run the test suite in Docker
	docker compose run --rm --build tests

# ----------------------------------------------------------------------------- Local (uv)
test-local: ## Run the tests locally (needs PostgreSQL, e.g. the db container: see .env.example)
	uv run pytest --cov

lint: ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

format: ## Fix lint issues and format the code
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## Static type checking (mypy --strict)
	uv run mypy

check: lint typecheck test-local ## Everything the CI runs

migrate: ## Apply migrations to the configured database
	uv run alembic upgrade head

revision: ## Generate a migration from model changes: make revision m="add sku to products"
	uv run alembic revision --autogenerate -m "$(m)"

seed: ## Load demo data into an empty database
	uv run python -m app.scripts.seed