"""FastAPI dependencies condivise."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db as _get_db
from .redis_client import get_redis as _get_redis


async def db_dep() -> AsyncIterator[AsyncSession]:
    async for session in _get_db():
        yield session


def redis_dep() -> Redis:
    return _get_redis()


# Type aliases per import più puliti negli endpoint
DB = Annotated[AsyncSession, Depends(db_dep)]
RedisDep = Annotated[Redis, Depends(redis_dep)]
