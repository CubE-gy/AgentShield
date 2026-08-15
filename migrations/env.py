from logging.config import fileConfig
import os
from pathlib import Path

from alembic import context
from dotenv import dotenv_values
from sqlalchemy import engine_from_config, pool

from app.models import Base


config = context.config

if (
    config.config_file_name is not None
    and config.attributes.get("configure_logger", True)
):
    fileConfig(config.config_file_name)

env_file_values = dotenv_values(Path.cwd() / ".env")
database_url = os.getenv("AGENTSHIELD_DEV_DATABASE_URL") or env_file_values.get(
    "AGENTSHIELD_DEV_DATABASE_URL"
)
if not database_url:
    raise RuntimeError("缺少 AGENTSHIELD_DEV_DATABASE_URL，无法执行数据库迁移")

config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """不创建数据库连接，仅生成迁移 SQL。"""

    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """连接数据库并执行迁移。"""

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
