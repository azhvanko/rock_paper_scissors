import asyncio

import click

from app.config import settings
from app.db import create_db_schema, drop_db_schema, recreate_db_schema


@click.group()
def cli() -> None:
    pass


@cli.command('create_db_schema')
@click.option('--db_uri', type=str, default=settings.SQLALCHEMY_DATABASE_URL)
def _create_db_schema(db_uri: str) -> None:
    asyncio.run(create_db_schema(db_uri))


@cli.command('drop_db_schema')
@click.option('--db_uri', type=str, default=settings.SQLALCHEMY_DATABASE_URL)
def _drop_db_schema(db_uri: str) -> None:
    asyncio.run(drop_db_schema(db_uri))


@cli.command('recreate_db_schema')
@click.option('--db_uri', type=str, default=settings.SQLALCHEMY_DATABASE_URL)
def _recreate_db_schema(db_uri: str) -> None:
    asyncio.run(recreate_db_schema(db_uri))
