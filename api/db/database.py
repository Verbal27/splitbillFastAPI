from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncAttrs,
)
from sqlalchemy.orm import DeclarativeBase, mapped_column
from typing import Annotated, AsyncGenerator
from api.core.config import settings
from datetime import datetime
from sqlalchemy import func


# DB engine
async_engine = create_async_engine(
    url=settings.DATABASE_URL_asyncpg,
    echo=True,
)

# Session engine
async_session_factory = async_sessionmaker(async_engine)


# Session creation
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


# Base class for models
class Base(AsyncAttrs, DeclarativeBase):
    pass


# Universal defined properties
intpk = Annotated[
    int,
    mapped_column(primary_key=True, unique=True, nullable=False, autoincrement=True),
]
created_at = Annotated[
    datetime, mapped_column(server_default=func.now(), nullable=False)
]
updated_at = Annotated[
    datetime,
    mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False),
]
