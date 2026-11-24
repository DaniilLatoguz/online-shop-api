from fastapi import APIRouter, Response, status

from app.api.deps import CartServiceDep, CurrentUserDep, ProductIdPath
from app.api.errors import problem_responses
from app.schemas.cart import CartItemCreate, CartItemUpdate, CartRead

router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("", summary="View the cart", responses=problem_responses(404, 422))
async def get_cart(user: CurrentUserDep, cart: CartServiceDep) -> CartRead:
    return CartRead.model_validate(await cart.get_cart(user.id))


@router.post(
    "/items",
    status_code=status.HTTP_201_CREATED,
    summary="Add a product to the cart",
    description="Creates a cart line (201). If the product is already in the cart, the quantity "
    "is added to the existing line (200). The resulting quantity is checked against the stock; "
    "a cart holds at most 100 different products (409 `cart_items_limit_exceeded`).",
    responses={
        status.HTTP_200_OK: {
            "model": CartRead,
            "description": "The product was already in the cart: its quantity was increased.",
        },
        **problem_responses(404, 409, 422),
    },
)
async def add_cart_item(
    payload: CartItemCreate, user: CurrentUserDep, cart: CartServiceDep, response: Response
) -> CartRead:
    updated_cart, created = await cart.add_item(user.id, payload.product_id, payload.quantity)
    if not created:
        response.status_code = status.HTTP_200_OK
    return CartRead.model_validate(updated_cart)


@router.patch(
    "/items/{product_id}",
    summary="Change the quantity of a product in the cart",
    responses=problem_responses(404, 409, 422),
)
async def update_cart_item(
    product_id: ProductIdPath,
    payload: CartItemUpdate,
    user: CurrentUserDep,
    cart: CartServiceDep,
) -> CartRead:
    return CartRead.model_validate(await cart.update_item(user.id, product_id, payload.quantity))


@router.delete(
    "/items/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a product from the cart",
    responses=problem_responses(404, 422),
)
async def remove_cart_item(
    product_id: ProductIdPath, user: CurrentUserDep, cart: CartServiceDep
) -> None:
    await cart.remove_item(user.id, product_id)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove all products from the cart",
    responses=problem_responses(404, 422),
)
async def clear_cart(user: CurrentUserDep, cart: CartServiceDep) -> None:
    await cart.clear(user.id)
