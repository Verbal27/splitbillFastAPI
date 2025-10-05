from api.db.database import Base, async_engine
from sqlalchemy.engine import Connection
from logging.config import fileConfig
from api.core.config import settings
from api.models.models import *  # noqa: F403
from alembic import context
from pathlib import Path
import asyncio
import sys

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))


# Metadata for Alembic autogenerate
target_metadata = Base.metadata

# Alembic config
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use the DATABASE_URL from your settings

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_asyncpg)


# Offline migration
def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# Online migration
async def run_migrations_online():
    async with async_engine.connect() as connection:
        await connection.run_sync(do_run_migrations)


def do_run_migrations(connection: Connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
