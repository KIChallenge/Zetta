from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.dependencies import COOKIE, CurrentUser, DbSession, set_session_cookie
from backend.guards import LOGIN_FAILURES, REGISTRATIONS
from backend.models import User
from backend.schemas import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from backend.security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def auth_response(request: Request, response: Response, user: User) -> AuthResponse:
    return AuthResponse(
        access_token=set_session_cookie(request, response, user),
        user=UserResponse.model_validate(user),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request, response: Response, db: DbSession) -> AuthResponse:
    REGISTRATIONS.take(request.client.host if request.client else "")
    user = User(
        email=body.email,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # shortcut: tells that the email has an account; hiding it needs a confirmation email.
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered") from None
    return auth_response(request, response, user)


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> AuthResponse:
    # Counted per email, not per address: behind the dev proxy every user has the same address.
    LOGIN_FAILURES.check(body.email)
    user = db.scalar(select(User).where(User.email == body.email))
    if not verify_password(body.password, user.password_hash if user else None):
        LOGIN_FAILURES.add(body.email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return auth_response(request, response, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: CurrentUser, response: Response, db: DbSession) -> None:
    """Ends the session on every device: a token copied elsewhere stops working too."""
    user.revoke_tokens()
    db.commit()
    response.delete_cookie(COOKIE)
