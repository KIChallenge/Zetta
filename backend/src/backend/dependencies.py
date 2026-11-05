from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import User
from backend.security import create_access_token, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]

# The browser keeps the token in an httpOnly cookie, out of reach of scripts. API clients and tests send a Bearer.
COOKIE = "lotse_session"
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def set_session_cookie(request: Request, response: Response, user: User) -> str:
    token = create_access_token(user.id, user.version)
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )
    return token


def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = credentials.credentials if credentials else request.cookies.get(COOKIE)
    if token is None:
        raise unauthorized
    # Another site can make the browser send the cookie, but not a custom header: that needs CORS, which it lacks.
    if credentials is None and request.method not in SAFE_METHODS and "x-requested-with" not in request.headers:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Missing X-Requested-With header")
    try:
        user_id, version = decode_access_token(token)
    except jwt.InvalidTokenError:
        raise unauthorized from None
    user = db.get(User, user_id)
    if user is None or version != user.version:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
