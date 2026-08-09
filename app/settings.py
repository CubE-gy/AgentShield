from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    dev_database_url: str
    test_database_url: str
    model_provider: str = "mock"
    model_api_key: str | None = None
    model_name: str = "test-model"
    model_base_url: str = "https://example.invalid"

    model_config = SettingsConfigDict(
        env_prefix="AGENTSHIELD_",
        env_file=".env",
        extra="ignore",
    )