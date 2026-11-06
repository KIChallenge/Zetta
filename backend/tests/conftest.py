import asyncio
import os
import tempfile
from pathlib import Path

# Must be set before anything imports backend.config.
test_dir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(test_dir.name) / 'test.db'}"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"
os.environ["LLM_API_KEY"] = "test-key"
os.environ["ALLOWED_HOSTS"] = '["testserver"]'

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.database import Base, engine
from backend.guards import reset_limits
from backend.llm import get_llm


class FakeLlm:
    """Stands in for the real LLM: tests never call the API."""

    def __init__(self):
        self.facts = {}  # what extract() finds in every message
        self.medical = False
        self.off_topic = False
        self.intro_text = "Hier sind die nächsten Schritte für Sie."
        self.script_text = None  # step input -> script dict; default: a valid script per step
        self.title_text = "Pflege für Mama"
        self.fail = False  # every call raises, like an LLM that is down
        self.hang = False
        self.calls = []  # (method, input) in call order
        self.letter_items = []  # what recommendations() finds in an uploaded letter

    async def _call(self, method, value):
        self.calls.append((method, value))
        if self.hang:
            await asyncio.Event().wait()
        if self.fail:
            raise RuntimeError("LLM down")

    async def extract(self, text, question, topics=None):
        await self._call("extract", {"text": text, "question": question})
        return {"medical_question": self.medical, "off_topic": self.off_topic, **self.facts}

    async def intro(self, plan, language):
        await self._call("intro", {**plan, "language": language})
        return self.intro_text

    async def scripts(self, steps, detail):
        await self._call("scripts", steps)
        return {step["step_id"]: (self.script_text or valid_script)(step) for step in steps}

    async def recommendations(self, letter):
        await self._call("recommendations", letter)
        return self.letter_items

    async def title(self, text):
        if self.title_text is None:
            raise RuntimeError("LLM down")
        return self.title_text


def valid_script(step):
    if step["type"] == "call":
        points = [{"covers": i["id"], "text": f"Wie ist das mit {i['id']}?"} for i in step["items"]]
        return {"call": {"opening": "Guten Tag, hier spricht {user.name}.", "points": points, "closing": "Danke."}}
    covers = [i["id"] for i in step["items"]]
    return {"email": {"subject": "Anfrage", "body": "Sehr geehrte Damen und Herren, ... {user.name}", "covers": covers}}


@pytest.fixture
def llm():
    fake = FakeLlm()
    app.dependency_overrides[get_llm] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


@pytest.fixture
def client(llm):
    Base.metadata.drop_all(engine)
    reset_limits()
    with TestClient(app) as test_client:
        # Tests sign in with the Bearer token; the session cookie has its own tests in test_auth.py.
        test_client.event_hooks = {"response": [lambda _: test_client.cookies.clear()]}
        yield test_client
