import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

ANNA = {
    "email": "anna@example.at",
    "password": "secret-password-123",
    "display_name": "Anna",
}
CREDENTIALS = {"email": ANNA["email"], "password": ANNA["password"]}
STARTUP_TIMEOUT_SECONDS = 15


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_until_ready(client, process, log_path):
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail(f"Server exited during startup:\n{log_path.read_text()}")
        try:
            client.get("/docs")
            return
        except httpx.TransportError:
            time.sleep(0.1)
    pytest.fail(f"Server did not start in time:\n{log_path.read_text()}")


@pytest.fixture
def server(tmp_path):
    port = free_port()
    log_path = tmp_path / "server.log"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'e2e.db'}",
        "JWT_SECRET": "e2e-secret-e2e-secret-e2e-secret-e2e-1234",
        "ALLOWED_HOSTS": '["127.0.0.1"]',
    }
    with log_path.open("w") as log:
        # cwd is the temp dir so a developer's backend/.env is not picked up.
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app:app", "--port", str(port)],
            cwd=tmp_path,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            wait_until_ready(client, process, log_path)
            yield client
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_register_login_and_me_over_http(server):
    registered = server.post("/auth/register", json=ANNA)
    assert registered.status_code == 201
    user = registered.json()["user"]
    assert user["email"] == ANNA["email"]
    assert user["display_name"] == ANNA["display_name"]

    duplicate = server.post("/auth/register", json=ANNA)
    assert duplicate.status_code == 409
    assert duplicate.json() == {"status": 409, "detail": "Email already registered"}

    rejected = server.post("/auth/login", json={**CREDENTIALS, "password": "wrong"})
    assert rejected.status_code == 401
    assert rejected.json() == {"status": 401, "detail": "Invalid email or password"}

    logged_in = server.post("/auth/login", json=CREDENTIALS)
    assert logged_in.status_code == 200
    assert logged_in.json()["user"] == user

    token = logged_in.json()["access_token"]
    me = server.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json() == user

    server.cookies.clear()  # the login also set the session cookie
    anonymous = server.get("/me")
    assert anonymous.status_code == 401
    assert anonymous.json()["status"] == 401
