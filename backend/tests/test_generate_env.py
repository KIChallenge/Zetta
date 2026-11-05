import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def backend_copy(tmp_path):
    (tmp_path / "scripts").mkdir()
    shutil.copy(BACKEND_DIR / "scripts" / "generate_env.py", tmp_path / "scripts")
    shutil.copy(BACKEND_DIR / ".env.example", tmp_path)
    return tmp_path


def run_script(backend_dir):
    return subprocess.run(
        [sys.executable, backend_dir / "scripts" / "generate_env.py"],
        capture_output=True,
        text=True,
    )


def test_generated_env_is_accepted_by_the_app(backend_copy):
    result = run_script(backend_copy)

    assert result.returncode == 0
    env = {key: value for key, value in os.environ.items() if key != "JWT_SECRET"}
    loaded = subprocess.run(
        [sys.executable, "-c", "from backend.config import settings; print(settings.jwt_secret)"],
        cwd=backend_copy,
        env=env,
        capture_output=True,
        text=True,
    )
    assert loaded.returncode == 0, loaded.stderr
    secret = loaded.stdout.strip()
    assert len(secret) == 64
    assert f"JWT_SECRET={secret}\n" in (backend_copy / ".env").read_text()
    assert secret not in result.stdout


def test_generated_env_is_only_readable_by_owner(backend_copy):
    run_script(backend_copy)

    assert stat.S_IMODE((backend_copy / ".env").stat().st_mode) == 0o600


def test_each_run_generates_a_different_secret(backend_copy):
    run_script(backend_copy)
    first = (backend_copy / ".env").read_text()
    (backend_copy / ".env").unlink()

    run_script(backend_copy)

    assert (backend_copy / ".env").read_text() != first


def test_existing_env_is_not_overwritten(backend_copy):
    env_path = backend_copy / ".env"
    env_path.write_text("JWT_SECRET=keep-me\n")

    result = run_script(backend_copy)

    assert result.returncode == 1
    assert "already exists" in result.stderr
    assert env_path.read_text() == "JWT_SECRET=keep-me\n"
