from dataclasses import dataclass
import hmac
import json
from collections.abc import Sequence


@dataclass(frozen=True)
class ApiKeyRecord:
    """一条 API Key 与租户的对应关系。"""

    value: str
    tenant_id: str
    is_active: bool


class ApiKeyAuthenticationError(Exception):
    """API Key 认证失败。"""

    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(error_code)


def authenticate_api_key(
    provided_key: str | None,
    records: Sequence[ApiKeyRecord],
) -> ApiKeyRecord:
    """验证 API Key，并返回认证后的租户记录。"""

    if not provided_key:
        raise ApiKeyAuthenticationError("API_KEY_MISSING")

    for record in records:
        if hmac.compare_digest(record.value, provided_key):
            if not record.is_active:
                raise ApiKeyAuthenticationError("API_KEY_DISABLED")

            return record

    raise ApiKeyAuthenticationError("API_KEY_INVALID")


def load_api_key_records(serialized_records: str) -> list[ApiKeyRecord]:
    """从 JSON 配置文本读取 API Key 记录。"""

    try:
        raw_records = json.loads(serialized_records)
    except json.JSONDecodeError as error:
        raise ValueError("API Key 配置格式错误") from error

    if not isinstance(raw_records, list):
        raise ValueError("API Key 配置必须是列表")

    records = []
    for raw_record in raw_records:
        if not isinstance(raw_record, dict):
            raise ValueError("API Key 配置项必须是对象")

        value = raw_record.get("value")
        tenant_id = raw_record.get("tenant_id")
        is_active = raw_record.get("is_active")

        if (
            not isinstance(value, str)
            or not value
            or not isinstance(tenant_id, str)
            or not tenant_id
            or not isinstance(is_active, bool)
        ):
            raise ValueError("API Key 配置项缺少有效字段")

        records.append(
            ApiKeyRecord(
                value=value,
                tenant_id=tenant_id,
                is_active=is_active,
            )
        )

    return records