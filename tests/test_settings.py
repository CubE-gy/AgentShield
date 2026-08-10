from pathlib import Path

from app.settings import Settings

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
