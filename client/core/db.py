import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.schema import CreateColumn

from core.config import settings

# Create Async Engine
engine = create_async_engine(
    settings.async_database_url, 
    echo=False,
    pool_pre_ping=True, 
    # poolclass=NullPool  <-- Removed to use default QueuePool
    pool_size=10, 
    max_overflow=20
)

# Create Session Factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()

logger = logging.getLogger(__name__)
_SCHEMA_BOOTSTRAP_LOCK_ID = 8024001
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"
_ALEMBIC_DIR = _REPO_ROOT / "alembic"


def _run_alembic_upgrade() -> None:
    alembic_cfg = Config(str(_ALEMBIC_INI))
    alembic_cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    command.upgrade(alembic_cfg, "head")


async def _bootstrap_schema_from_metadata() -> None:
    from . import models as _models  # noqa: F401

    def _sync_schema(sync_connection) -> None:
        Base.metadata.create_all(bind=sync_connection)

        inspector = inspect(sync_connection)
        preparer = sync_connection.dialect.identifier_preparer

        for table in Base.metadata.sorted_tables:
            existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue

                column_sql = str(CreateColumn(column).compile(dialect=sync_connection.dialect)).strip()
                sync_connection.exec_driver_sql(
                    f"ALTER TABLE {preparer.quote(table.name)} ADD COLUMN IF NOT EXISTS {column_sql}"
                )
                logger.info(
                    "Added missing column %s.%s during startup schema sync",
                    table.name,
                    column.name,
                )

    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT pg_advisory_lock(:lock_id)"),
            {"lock_id": _SCHEMA_BOOTSTRAP_LOCK_ID},
        )
        try:
            await connection.run_sync(_sync_schema)
        finally:
            await connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": _SCHEMA_BOOTSTRAP_LOCK_ID},
            )


async def run_startup_migrations() -> None:
    if _ALEMBIC_INI.exists() and _ALEMBIC_DIR.exists():
        await asyncio.to_thread(_run_alembic_upgrade)
        return

    logger.warning(
        "Alembic files were not found under %s; bootstrapping schema from metadata.",
        _REPO_ROOT,
    )
    await _bootstrap_schema_from_metadata()

# Dependency for FastAPI
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
