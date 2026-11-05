from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = Field(min_length=32)
    jwt_expire_minutes: int = 60 * 24
    database_url: str = "sqlite:///./zetta.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    azure_openai_endpoint: str = (
        "https://aif-dvsv-dev-hackathon-01-we-12.services.ai.azure.com/openai/v1"
    )
    azure_openai_api_key: str = Field(min_length=1, repr=False)
    azure_openai_model: str = "gpt-5-4-mini"


settings = Settings()
