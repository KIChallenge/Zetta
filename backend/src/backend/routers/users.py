from fastapi import APIRouter

from backend.dependencies import CurrentUser
from backend.schemas import UserResponse

router = APIRouter(tags=["users"])


@router.get("/me")
def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
