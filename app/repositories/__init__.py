"""Data access layer: SQL queries only. Repositories never commit; services own transactions."""

from app.repositories.product import ProductRepository
from app.repositories.user import UserRepository

__all__ = ["ProductRepository", "UserRepository"]
