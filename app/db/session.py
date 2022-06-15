import typing as t
from types import TracebackType

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.logging import logger


class DBSession:
    _engine: AsyncEngine
    _session: AsyncSession

    def __init__(self, echo: bool = settings.BATTLE_DEBUG):
        self._engine = create_async_engine(
            settings.SQLALCHEMY_DATABASE_URL,
            echo=echo
        )

    async def __aenter__(self) -> AsyncSession:
        self._session = sessionmaker(
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            class_=AsyncSession,
            bind=self._engine
        )()
        return self._session

    async def __aexit__(
        self,
        exc_type: t.Optional[type],
        exc_val: t.Optional[Exception],
        exc_tb: t.Optional[TracebackType]
    ) -> None:
        if exc_val is not None:
            logger.exception(exc_val)
        if self._session:
            if exc_val is not None:
                await self._session.rollback()
            await self._session.close()


async def get_db_session() -> t.AsyncIterator[AsyncSession]:
    async with DBSession() as db_session:
        yield db_session
