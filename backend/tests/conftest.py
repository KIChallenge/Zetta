import os
import tempfile
from pathlib import Path

# Must be set before anything imports backend.config.
test_dir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(test_dir.name) / 'test.db'}"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.database import Base, engine


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as test_client:
        yield test_client
