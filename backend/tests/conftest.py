import asyncio
import os
import tempfile
from pathlib import Path

# Must be set before anything imports backend.config.
test_dir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(test_dir.name) / 'test.db'}"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"
os.environ["AZURE_OPENAI_API_KEY"] = "test-key"

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.database import Base, engine
from backend.llm import get_llm


class FakeLlm:
    """Stands in for the real LLM: tests never call the API."""

    def __init__(self):
        self.deltas = ["Hallo", " Anna", "!"]
        self.title_text = "Pflege für Mama"
        self.fail = False
        self.hang = False
        self.histories = []

    async def reply(self, history):
        self.histories.append(history)
        for delta in self.deltas:
            yield delta
        if self.fail:
            raise RuntimeError("LLM down")
        if self.hang:
            await asyncio.Event().wait()

    async def title(self, text):
        if self.title_text is None:
            raise RuntimeError("LLM down")
        return self.title_text


@pytest.fixture
def llm():
    fake = FakeLlm()
    app.dependency_overrides[get_llm] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


@pytest.fixture
def client(llm):
    Base.metadata.drop_all(engine)
    with TestClient(app) as test_client:
        yield test_client
