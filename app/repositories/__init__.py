"""Data access layer: SQL queries only. Repositories never commit; services own transactions."""

from app.repositories.user import UserRepository

__all__ = ["UserRepository"]
