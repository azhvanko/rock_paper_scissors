import click

from app.cli.db import cli as db_cli


cli = click.CommandCollection(sources=[db_cli,])
