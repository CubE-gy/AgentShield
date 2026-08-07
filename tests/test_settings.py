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

    settings = Settings()

    assert settings.dev_database_url.endswith("/dev_db")
    assert settings.test_database_url.endswith("/test_db")