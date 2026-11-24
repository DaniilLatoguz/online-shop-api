from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ProductNotFoundError
from app.models import Product
from app.repositories import ProductRepository
from app.schemas.product import ProductCreate, ProductListParams, ProductUpdate


class ProductService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._products = ProductRepository(session)

    async def create(self, data: ProductCreate) -> Product:
        product = Product(
            name=data.name,
            description=data.description,
            price=data.price,
            stock=data.stock,
        )
        self._products.add(product)
        await self._session.commit()
        return product

    async def get(self, product_id: int) -> Product:
        product = await self._products.get(product_id)
        if product is None:
            raise ProductNotFoundError(product_id)
        return product

    async def update(self, product_id: int, data: ProductUpdate) -> Product:
        product = await self.get(product_id)
        # exclude_unset: only fields that were actually sent are applied (partial update).
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(product, field, value)
        await self._session.commit()
        return product

    async def list(self, params: ProductListParams) -> tuple[Sequence[Product], int]:
        products = await self._products.list(params)
        total = await self._products.count(params)
        return products, total
