from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app import app
from backend.config import settings
from backend.database import SessionLocal
from backend.models import User
from backend.security import JWT_ALGORITHM, create_access_token

ANNA = {
    "email": "anna@example.at",
    "password": "secret-password-123",
    "display_name": "Anna",
}
CREDENTIALS = {"email": ANNA["email"], "password": ANNA["password"]}


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def assert_error(response, status, detail=None):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"status", "detail"}
    assert body["status"] == status
    assert isinstance(body["detail"], str)
    if detail is not None:
        assert body["detail"] == detail


def test_register_returns_token_and_user(client):
    response = client.post("/auth/register", json=ANNA)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"access_token", "user"}
    assert set(body["user"]) == {"id", "email", "display_name"}
    assert body["user"]["email"] == "anna@example.at"
    assert body["user"]["display_name"] == "Anna"


def test_register_stores_hashed_password(client):
    client.post("/auth/register", json=ANNA)

    with SessionLocal() as db:
        user = db.scalar(select(User))
    assert ANNA["password"] not in user.password_hash
    assert user.password_hash.startswith("$argon2")


def test_register_duplicate_email_is_case_insensitive(client):
    client.post("/auth/register", json=ANNA)

    response = client.post("/auth/register", json={**ANNA, "email": "ANNA@example.at"})

    assert_error(response, 409, "Email already registered")


def test_register_validation_error_format_does_not_echo_password(client):
    response = client.post(
        "/auth/register", json={"email": "not-an-email", "password": "short7!", "display_name": " "}
    )

    assert_error(response, 422)
    detail = response.json()["detail"]
    assert "email" in detail and "password" in detail and "display_name" in detail
    assert "short7!" not in detail


def test_register_malformed_json(client):
    response = client.post(
        "/auth/register", content="{", headers={"Content-Type": "application/json"}
    )

    assert_error(response, 422, "JSON decode error")


def test_login_returns_token_and_user(client):
    registered = client.post("/auth/register", json=ANNA).json()

    response = client.post("/auth/login", json=CREDENTIALS)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "user"}
    assert body["user"] == registered["user"]


def test_login_email_is_case_insensitive(client):
    client.post("/auth/register", json=ANNA)

    response = client.post("/auth/login", json={**CREDENTIALS, "email": "Anna@Example.at"})

    assert response.status_code == 200


def test_login_wrong_password_and_unknown_email_look_the_same(client):
    client.post("/auth/register", json=ANNA)

    wrong_password = client.post("/auth/login", json={**CREDENTIALS, "password": "wrong"})
    unknown_email = client.post("/auth/login", json={**CREDENTIALS, "email": "bob@example.at"})

    assert_error(wrong_password, 401, "Invalid email or password")
    assert_error(unknown_email, 401, "Invalid email or password")


def test_me_returns_current_user(client):
    registered = client.post("/auth/register", json=ANNA).json()

    response = client.get("/me", headers=bearer(registered["access_token"]))

    assert response.status_code == 200
    assert response.json() == registered["user"]


def test_me_accepts_login_token(client):
    registered = client.post("/auth/register", json=ANNA).json()
    token = client.post("/auth/login", json=CREDENTIALS).json()["access_token"]

    response = client.get("/me", headers=bearer(token))

    assert response.json() == registered["user"]


def test_me_without_token(client):
    response = client.get("/me")

    assert_error(response, 401)
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_rejects_garbage_token(client):
    assert_error(client.get("/me", headers=bearer("garbage")), 401)


def test_me_rejects_expired_token(client):
    user_id = client.post("/auth/register", json=ANNA).json()["user"]["id"]
    token = jwt.encode(
        {"sub": user_id, "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.jwt_secret,
        algorithm=JWT_ALGORITHM,
    )

    assert_error(client.get("/me", headers=bearer(token)), 401)


def test_me_rejects_token_signed_with_other_secret(client):
    user_id = client.post("/auth/register", json=ANNA).json()["user"]["id"]
    token = jwt.encode(
        {"sub": user_id, "exp": datetime.now(UTC) + timedelta(minutes=1)},
        "other-secret-other-secret-other-secret-1",
        algorithm=JWT_ALGORITHM,
    )

    assert_error(client.get("/me", headers=bearer(token)), 401)


def test_me_rejects_unsigned_token(client):
    user_id = client.post("/auth/register", json=ANNA).json()["user"]["id"]
    token = jwt.encode(
        {"sub": user_id, "exp": datetime.now(UTC) + timedelta(minutes=1)}, None, algorithm="none"
    )

    assert_error(client.get("/me", headers=bearer(token)), 401)


def test_me_rejects_token_of_unknown_user(client):
    assert_error(client.get("/me", headers=bearer(create_access_token("no-such-user"))), 401)


def test_unknown_route_uses_error_format(client):
    assert_error(client.get("/does-not-exist"), 404)


def test_unsupported_method_uses_error_format(client):
    assert_error(client.get("/auth/login"), 405)


def test_unhandled_exception_uses_error_format(monkeypatch):
    def fail(*_):
        raise RuntimeError("secret internals")

    monkeypatch.setattr("backend.routers.auth.hash_password", fail)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/auth/register", json=ANNA)

    assert_error(response, 500, "Internal server error")
