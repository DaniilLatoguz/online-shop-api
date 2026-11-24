from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UserNotFoundError
from app.models import User
from app.repositories import UserRepository
from app.schemas.user import UserCreate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    async def create(self, data: UserCreate) -> User:
        user = User(name=data.name)
        self._users.add(user)
        await self._session.commit()
        return user

    async def get(self, user_id: int) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user
