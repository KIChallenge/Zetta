from fastapi import APIRouter, HTTPException, status

from backend.dependencies import CurrentUser, DbSession
from backend.models import Profile, User
from backend.schemas import DeleteAccountRequest, PasswordChangeRequest, ProfileData, UserResponse
from backend.security import hash_password, verify_password

router = APIRouter(tags=["users"])


def check_password(user: User, password: str) -> None:
    # 403, not 401: the frontend logs out on 401, and the session itself is fine.
    if not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Wrong password")


@router.get("/me")
def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.get("/me/profile")
def get_profile(user: CurrentUser) -> ProfileData:
    return ProfileData.model_validate(user.profile) if user.profile else ProfileData()


@router.put("/me/profile")
def put_profile(body: ProfileData, user: CurrentUser, db: DbSession) -> ProfileData:
    db.merge(Profile(user_id=user.id, **body.model_dump()))
    db.commit()
    return body


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChangeRequest, user: CurrentUser, db: DbSession) -> None:
    check_password(user, body.current_password)
    user.password_hash = hash_password(body.new_password)
    db.commit()


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(body: DeleteAccountRequest, user: CurrentUser, db: DbSession) -> None:
    check_password(user, body.password)
    db.delete(user)  # with its profile, chats and their messages (ORM cascade)
    db.commit()
