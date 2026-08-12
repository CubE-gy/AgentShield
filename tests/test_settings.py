from pathlib import Path
import pytest

from app.settings import Settings
from app.authentication import ApiKeyRecord

def test_settings_reads_database_urls_from_environment(monkeypatch):
    monkeypatch.setenv(
        "AGENTSHIELD_DEV_DATABASE_URL",
        "postgresql+psycopg://dev_user:dev_password@127.0.0.1:5432/dev_db",
    )
    monkeypatch.setenv(
        "AGENTSHIELD_TEST_DATABASE_URL",
        "postgresql+psycopg://test_user:test_password@127.0.0.1:5433/test_db",
    )

    settings = Settings(_env_file=None)

    assert settings.dev_database_url.endswith("/dev_db")
    assert settings.test_database_url.endswith("/test_db")

def test_settings_default_to_mock_provider(monkeypatch):
    monkeypatch.setenv(
        "AGENTSHIELD_DEV_DATABASE_URL",
        "postgresql+psycopg://dev_user:dev_password@127.0.0.1:5432/dev_db",
    )
    monkeypatch.setenv(
        "AGENTSHIELD_TEST_DATABASE_URL",
        "postgresql+psycopg://test_user:test_password@127.0.0.1:5433/test_db",
    )

    settings = Settings(_env_file=None)

    assert settings.model_provider == "mock"

def test_settings_can_select_real_provider(monkeypatch):
    monkeypatch.setenv(
        "AGENTSHIELD_DEV_DATABASE_URL",
        "postgresql+psycopg://dev_user:dev_password@127.0.0.1:5432/dev_db",
    )
    monkeypatch.setenv(
        "AGENTSHIELD_TEST_DATABASE_URL",
        "postgresql+psycopg://test_user:test_password@127.0.0.1:5433/test_db",
    )
    monkeypatch.setenv(
        "AGENTSHIELD_MODEL_PROVIDER",
        "real",
    )

    settings = Settings(_env_file=None)

    assert settings.model_provider == "real"

def test_env_example_contains_safe_model_configuration():
    env_example = Path(".env.example").read_text(
        encoding="utf-8",
    )

    assert "AGENTSHIELD_MODEL_PROVIDER=mock" in env_example
    assert "AGENTSHIELD_MODEL_API_KEY=" in env_example
    assert "AGENTSHIELD_MODEL_NAME=gpt-5.6-terra" in env_example
    assert (
        "AGENTSHIELD_MODEL_BASE_URL=https://api.openai.com/v1"
        in env_example
    )
    assert "sk-" not in env_example

def test_settings_reads_api_key_records_from_environment(monkeypatch):
    monkeypatch.setenv(
        "AGENTSHIELD_DEV_DATABASE_URL",
        "postgresql+psycopg://dev_user:dev_password@127.0.0.1:5432/dev_db",
    )
    monkeypatch.setenv(
        "AGENTSHIELD_TEST_DATABASE_URL",
        "postgresql+psycopg://test_user:test_password@127.0.0.1:5433/test_db",
    )
    monkeypatch.setenv(
        "AGENTSHIELD_API_KEY_RECORDS",
        (
            '[{"value": "test-key", "tenant_id": "tenant-alpha", '
            '"is_active": true}]'
        ),
    )

    settings = Settings(_env_file=None)

    assert settings.api_key_records == [
        ApiKeyRecord(
            value="test-key",
            tenant_id="tenant-alpha",
            is_active=True,
        )
    ]


def test_settings_rejects_invalid_api_key_configuration(monkeypatch):
    monkeypatch.setenv(
        "AGENTSHIELD_DEV_DATABASE_URL",
        "postgresql+psycopg://dev_user:dev_password@127.0.0.1:5432/dev_db",
    )
    monkeypatch.setenv(
        "AGENTSHIELD_TEST_DATABASE_URL",
        "postgresql+psycopg://test_user:test_password@127.0.0.1:5433/test_db",
    )
    monkeypatch.setenv(
        "AGENTSHIELD_API_KEY_RECORDS",
        "not-json",
    )

    settings = Settings(_env_file=None)

    with pytest.raises(ValueError, match="API Key 配置格式错误"):
        _ = settings.api_key_records


def test_env_example_contains_empty_api_key_records():
    env_example = Path(".env.example").read_text(
        encoding="utf-8",
    )

    assert "AGENTSHIELD_API_KEY_RECORDS=[]" in env_example


def test_settings_reads_tool_allowlist_from_environment(monkeypatch):
    monkeypatch.setenv(
        "AGENTSHIELD_DEV_DATABASE_URL",
        "postgresql+psycopg://dev_user:dev_password@127.0.0.1:5432/dev_db",
    )
    monkeypatch.setenv(
        "AGENTSHIELD_TEST_DATABASE_URL",
        "postgresql+psycopg://test_user:test_password@127.0.0.1:5433/test_db",
    )
    monkeypatch.setenv(
        "AGENTSHIELD_ALLOWED_TOOLS",
        '["order_lookup"]',
    )

    settings = Settings(_env_file=None)

    assert settings.allowed_tools == ("order_lookup",)


def test_env_example_contains_empty_tool_allowlist():
    env_example = Path(".env.example").read_text(
        encoding="utf-8",
    )

    assert "AGENTSHIELD_ALLOWED_TOOLS=[]" in env_example
