from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.authentication import ApiKeyRecord, load_api_key_records


class Settings(BaseSettings):
    dev_database_url: str
    test_database_url: str
    model_provider: str = "mock"
    model_api_key: str | None = None
    model_name: str = "test-model"
    model_base_url: str = "https://example.invalid"
    api_key_records_raw: str = Field(
        default="[]",
        validation_alias="AGENTSHIELD_API_KEY_RECORDS",
    )

    model_config = SettingsConfigDict(
        env_prefix="AGENTSHIELD_",
        env_file=".env",
        extra="ignore",
    )

    @property
    def api_key_records(self) -> list[ApiKeyRecord]:
        """读取并检查本机配置中的 API Key 记录。"""

        return load_api_key_records(self.api_key_records_raw)
