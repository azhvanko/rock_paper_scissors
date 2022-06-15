from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.declarative import declarative_base

from app.config import settings


DeclarativeBase = declarative_base()


async def create_db_schema(db_uri: str, echo: bool = settings.BATTLE_DEBUG) -> None:
    engine = create_async_engine(db_uri, echo=echo)
    async with engine.begin() as connection:
        await connection.run_sync(DeclarativeBase.metadata.create_all)


async def drop_db_schema(db_uri: str, echo: bool = settings.BATTLE_DEBUG) -> None:
    engine = create_async_engine(db_uri, echo=echo)
    async with engine.begin() as connection:
        await connection.run_sync(DeclarativeBase.metadata.drop_all)


async def recreate_db_schema(db_uri: str, echo: bool = settings.BATTLE_DEBUG) -> None:
    await drop_db_schema(db_uri, echo)
    await create_db_schema(db_uri, echo)
