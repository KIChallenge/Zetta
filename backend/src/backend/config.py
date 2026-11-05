from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = Field(min_length=32)
    jwt_expire_minutes: int = 60 * 24
    database_url: str = "sqlite:///./zetta.db"
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
