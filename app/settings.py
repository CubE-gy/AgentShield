import json

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
    allowed_tools_raw: str = Field(
        default="[]",
        validation_alias="AGENTSHIELD_ALLOWED_TOOLS",
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

    @property
    def allowed_tools(self) -> tuple[str, ...]:
        """读取并检查本机配置允许的工具名称。"""

        try:
            raw_tools = json.loads(self.allowed_tools_raw)
        except json.JSONDecodeError as error:
            raise ValueError("工具允许名单配置格式错误") from error

        if (
            not isinstance(raw_tools, list)
            or any(
                not isinstance(tool_name, str) or not tool_name
                for tool_name in raw_tools
            )
        ):
            raise ValueError("工具允许名单必须是非空字符串数组")

        return tuple(raw_tools)
