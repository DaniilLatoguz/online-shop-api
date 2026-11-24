from fastapi import APIRouter, Request, Response, status

from app.api.deps import UserIdPath, UserServiceDep
from app.api.errors import problem_responses
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a user",
    responses=problem_responses(422),
)
async def create_user(
    payload: UserCreate, users: UserServiceDep, request: Request, response: Response
) -> UserRead:
    user = await users.create(payload)
    response.headers["Location"] = str(request.url_for("get_user", user_id=user.id))
    return UserRead.model_validate(user)


@router.get("/{user_id}", summary="Get a user", responses=problem_responses(404, 422))
async def get_user(user_id: UserIdPath, users: UserServiceDep) -> UserRead:
    return UserRead.model_validate(await users.get(user_id))
