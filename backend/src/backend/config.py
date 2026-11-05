from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_LLM_URL = "https://aif-dvsv-dev-hackathon-01-we-12.services.ai.azure.com/openai/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = Field(min_length=32)
    jwt_expire_minutes: int = 60 * 24
    database_url: str = "sqlite:///./zetta.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    # Any OpenAI-compatible server. Not called OPENAI_*: shells and other tools set those, and the environment beats
    # .env, so a stray OPENAI_BASE_URL would send every chat elsewhere. The AZURE_ names are older and still work.
    llm_base_url: str = Field(
        DEFAULT_LLM_URL, validation_alias=AliasChoices("LLM_BASE_URL", "AZURE_OPENAI_ENDPOINT")
    )
    llm_api_key: str = Field("", repr=False, validation_alias=AliasChoices("LLM_API_KEY", "AZURE_OPENAI_API_KEY"))
    llm_model: str = Field("gpt-5-4-mini", validation_alias=AliasChoices("LLM_MODEL", "AZURE_OPENAI_MODEL"))

    # Extra fields for every request, for what a server needs beyond the OpenAI API.
    llm_extra_body: dict = {}

    @model_validator(mode="after")
    def check_api_key(self) -> "Settings":
        # A local server may need no key, the default endpoint does: better to fail at startup than on every reply.
        if not self.llm_api_key and self.llm_base_url == DEFAULT_LLM_URL:
            raise ValueError("LLM_API_KEY is required for the default endpoint")
        return self


settings = Settings()
