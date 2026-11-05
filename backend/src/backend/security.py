from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from backend.config import settings

JWT_ALGORITHM = "HS256"

hasher = PasswordHasher()
# Verified against when the email is unknown, so login takes the same time
# whether or not the account exists.
DUMMY_HASH = hasher.hash("dummy-password")


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        hasher.verify(password_hash or DUMMY_HASH, password)
    except VerifyMismatchError:
        return False
    return password_hash is not None


def create_access_token(user_id: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Return the user id from the token. Raises jwt.InvalidTokenError if it is not valid."""
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
    return payload["sub"]
