from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


TEST_DATABASE_URL = (
    "postgresql+psycopg://"
    "agentshield_test:test_password_change_me@127.0.0.1:5433/agentshield_test"
)
INITIAL_REVISION = "20260814_0001"


def test_postgresql_migration_can_upgrade_and_downgrade(monkeypatch) -> None:
    """首份迁移应在测试 PostgreSQL 中创建、回滚并恢复审计表。"""

    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS audit_records"))
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

    monkeypatch.setenv("AGENTSHIELD_DEV_DATABASE_URL", TEST_DATABASE_URL)
    config = Config("alembic.ini")
    config.attributes["configure_logger"] = False

    try:
        command.upgrade(config, "head")
        assert "audit_records" in inspect(engine).get_table_names()

        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version"))
                .scalar_one()
                == INITIAL_REVISION
            )

        command.downgrade(config, "base")
        assert "audit_records" not in inspect(engine).get_table_names()
    finally:
        command.upgrade(config, "head")
        engine.dispose()
