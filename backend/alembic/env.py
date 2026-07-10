from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.models.base import Base

config = context.config
settings = get_settings()
if settings.mysql_database != "dawenzhang":
    raise RuntimeError("Alembic refuses to run outside the dawenzhang database")
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.sqlalchemy_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        actual_database = connection.exec_driver_sql("SELECT DATABASE()").scalar_one_or_none()
        if actual_database != "dawenzhang":
            raise RuntimeError(f"Alembic connected to unexpected database: {actual_database!r}")
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

