"""The LLM server is set in .env: any OpenAI-compatible URL, with the older AZURE_ names still working."""

import pytest
from pydantic import ValidationError

from backend.config import DEFAULT_LLM_URL, Settings

NAMES = ["LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_EXTRA_BODY", "OPENAI_BASE_URL", "OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_MODEL"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)


def settings() -> Settings:
    return Settings(_env_file=None)


def test_a_local_server_needs_only_its_url_and_model(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://192.168.1.51:9931/v1")
    monkeypatch.setenv("LLM_MODEL", "gemma")

    loaded = settings()

    assert (loaded.llm_base_url, loaded.llm_model, loaded.llm_api_key) == ("http://192.168.1.51:9931/v1", "gemma", "")


def test_the_default_endpoint_needs_a_key(monkeypatch):
    with pytest.raises(ValidationError, match="LLM_API_KEY"):
        settings()

    monkeypatch.setenv("LLM_API_KEY", "secret")
    assert settings().llm_base_url == DEFAULT_LLM_URL


def test_the_older_names_still_work(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.at/v1")
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "old")

    loaded = settings()

    assert (loaded.llm_api_key, loaded.llm_base_url, loaded.llm_model) == ("secret", "https://example.at/v1", "old")


def test_the_new_name_wins_over_the_older_one(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://new/v1")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "http://old/v1")

    assert settings().llm_base_url == "http://new/v1"


def test_the_key_never_shows_up_in_logs(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-do-not-log")

    assert "sk-do-not-log" not in repr(settings())


def test_the_url_in_env_file_wins_over_a_stray_openai_variable(monkeypatch, tmp_path):
    """Shells and other tools set OPENAI_BASE_URL. It must not redirect the app's chats."""
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:8787/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "someone-elses-key")
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_BASE_URL=http://192.168.1.51:9931/v1\n")

    loaded = Settings(_env_file=env_file)

    assert (loaded.llm_base_url, loaded.llm_api_key) == ("http://192.168.1.51:9931/v1", "")


def test_extra_body_is_read_as_json(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_API_KEY", "x")
    env_file = tmp_path / ".env"
    env_file.write_text('LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}\n')

    assert Settings(_env_file=env_file).llm_extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
