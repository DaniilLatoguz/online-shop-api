# Online Shop API

REST API (backend only) for a simplified online shop: users, products, a cart and orders.

**Stack:** Python 3.11+ · FastAPI · PostgreSQL 16 · SQLAlchemy 2.0 (async, asyncpg) · Alembic ·
Pydantic v2 · Docker Compose · pytest · uv · Ruff · mypy (strict)

## Run

```bash
docker compose up --build
```

Compose starts PostgreSQL, applies the migrations and loads demo data (users **1 Alice** and
**2 Bob**, 8 products), then starts the API. Swagger UI: http://localhost:8000/docs. Cart and order
requests identify the user by the `X-User-Id` header:

```bash
curl -X POST localhost:8000/cart/items -H "X-User-Id: 1" -H "Content-Type: application/json" \
     -d '{"product_id": 1, "quantity": 2}'
curl -X POST localhost:8000/orders -H "X-User-Id: 1"    # checkout: the cart becomes an order
```

Tests (198, on real PostgreSQL, 98 % coverage): `docker compose run --rm tests` or `make test`.

## Key decisions

1. **Layers:** routers (HTTP only) → services (business rules, transaction boundaries) →
   repositories (queries only). Pydantic schemas are separate from the ORM models.
   [More](docs/decisions.md#architecture)
2. **Services commit explicitly:** FastAPI runs dependency teardown after the response is sent, so a
   commit there could fail after the client got `201`.
   [More](docs/decisions.md#why-services-commit-and-the-session-dependency-does-not)
3. **Async SQLAlchemy without hidden I/O:** `lazy="raise"` relationships, explicit eager loading,
   `expire_on_commit=False`. [More](docs/decisions.md#async-sqlalchemy-20)
4. **The schema comes only from Alembic migrations**, never `create_all()`. The tests build their
   database with the migrations, and CI runs `alembic check`. [More](docs/decisions.md#database-schema)
5. **Money** is `NUMERIC` / `Decimal`, never `float`, and is returned as a string (`"19.90"`).
   [More](docs/decisions.md#money)
6. **Checkout is one transaction:** it locks the cart lines (`FOR UPDATE`) and the products
   (`FOR NO KEY UPDATE`, ascending id order), re-checks stock under the locks and copies the current
   name and price into the order. Add to cart is a single `INSERT … ON CONFLICT DO UPDATE`.
   [More](docs/decisions.md#transactions-and-concurrency)
7. **Stock** is optional per product (`null` = not tracked): checked when adding to the cart,
   written off at checkout, returned on cancellation; the cart does not reserve it. A cart line holds
   at most 1000 units, and an order at most 100 lines (checked when adding to the cart, enforced at
   checkout), so every total fits `NUMERIC(16, 2)`. [More](docs/decisions.md#stock)
8. **Order statuses** `created → paid | cancelled` change through action endpoints
   (`POST /orders/{id}/pay`, `/cancel`) under an order row lock, not through a free `PATCH`.
   [More](docs/decisions.md#order-statuses)
9. **HTTP statuses:** the assignment's 200/201/204/400/404/422 plus **409** for conflicts with the
   current state (stock, cart limits, order status). Another user's order is 404, not 403.
   [More](docs/decisions.md#http-status-codes)
10. **Errors** use one format, RFC 9457 `application/problem+json`, with a stable `code`.
    [More](docs/decisions.md#errors)
11. **Strict input:** unknown body fields and query parameters give 422, integers in the body are
    strict, and `PATCH` tells "not sent" from `null`. [More](docs/decisions.md#validation)
12. **`GET /health`** checks the database with a 2.5 s timeout and answers 503 when it is
    unavailable. [More](docs/decisions.md#health-check)
13. **Tests run on real PostgreSQL**, no SQLite or mocks: the "add to cart → place order" scenario,
    race conditions in real concurrent transactions, migrations up and down.
    [More](docs/decisions.md#running-the-tests)

Everything else (the endpoint list, error examples, local development without Docker, project
structure, trade-offs and next steps) is in [docs/decisions.md](docs/decisions.md).