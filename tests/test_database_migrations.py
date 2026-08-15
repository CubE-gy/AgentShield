from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_initial_migration_can_upgrade_and_downgrade(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """首份迁移应能创建并回滚审计记录表。"""

    database_path = tmp_path / "migration-test.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("AGENTSHIELD_DEV_DATABASE_URL", database_url)
    config = Config("alembic.ini")
    config.attributes["configure_logger"] = False

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    assert "audit_records" in inspect(engine).get_table_names()

    command.downgrade(config, "base")

    assert "audit_records" not in inspect(engine).get_table_names()
    engine.dispose()
