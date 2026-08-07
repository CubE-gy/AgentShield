from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    dev_database_url: str
    test_database_url: str

    model_config = SettingsConfigDict(
        env_prefix="AGENTSHIELD_",
        env_file=".env",
        extra="ignore",
    )