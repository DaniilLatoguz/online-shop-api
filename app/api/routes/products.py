from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status

from app.api.deps import ProductIdPath, ProductServiceDep
from app.api.errors import problem_responses
from app.schemas.common import Page
from app.schemas.product import ProductCreate, ProductListParams, ProductRead, ProductUpdate

router = APIRouter(prefix="/products", tags=["products"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a product",
    responses=problem_responses(422),
)
async def create_product(
    payload: ProductCreate, products: ProductServiceDep, request: Request, response: Response
) -> ProductRead:
    product = await products.create(payload)
    response.headers["Location"] = str(request.url_for("get_product", product_id=product.id))
    return ProductRead.model_validate(product)


@router.get(
    "",
    summary="List products (pagination, filtering, sorting)",
    responses=problem_responses(422),
)
async def list_products(
    params: Annotated[ProductListParams, Query()], products: ProductServiceDep
) -> Page[ProductRead]:
    items, total = await products.list(params)
    return Page[ProductRead](
        items=[ProductRead.model_validate(product) for product in items],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/{product_id}", summary="Get a product", responses=problem_responses(404, 422))
async def get_product(product_id: ProductIdPath, products: ProductServiceDep) -> ProductRead:
    return ProductRead.model_validate(await products.get(product_id))


@router.patch(
    "/{product_id}",
    summary="Update a product (partial update)",
    description="Only the fields present in the body are changed. "
    "Existing orders are not affected: they keep the price from the moment of checkout.",
    responses=problem_responses(404, 422),
)
async def update_product(
    product_id: ProductIdPath, payload: ProductUpdate, products: ProductServiceDep
) -> ProductRead:
    return ProductRead.model_validate(await products.update(product_id, payload))
