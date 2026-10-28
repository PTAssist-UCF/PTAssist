"""Tests for the migrations themselves: they match the models and work both ways."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select

from app.db import engine
from app.models import Base, Exercise


def table_names() -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def test_models_match_the_migrations(database: None) -> None:
    """A model changed without a migration (or the other way round) fails here."""
    with engine.connect() as connection:
        differences = compare_metadata(
            MigrationContext.configure(connection), Base.metadata
        )

    assert differences == []


def test_downgrade_and_upgrade_from_an_empty_database(
    database: None, alembic_config: Config
) -> None:
    command.downgrade(alembic_config, "base")
    assert table_names() == set()

    command.upgrade(alembic_config, "head")  # leaves the schema as other tests expect

    assert table_names() == {table.name for table in Base.metadata.sorted_tables}
    with engine.connect() as connection:
        names = connection.scalars(select(Exercise.name)).all()
    assert len(names) == 5  # the exercise library is filled in again
