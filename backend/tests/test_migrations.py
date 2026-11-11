"""Tests for the migrations themselves: they match the models and work both ways."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import engine
from app.models import (
    Base,
    Exercise,
    ExerciseSession,
    Plan,
    PlanExercise,
    Role,
    User,
)


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


def test_a_session_without_a_video_key_stops_the_migration_that_requires_one(
    db: Session, alembic_config: Config
) -> None:
    """163e3f3a47c4 refuses such a session and changes nothing, instead of deleting it
    (and its results)."""
    command.downgrade(alembic_config, "e846d97b14af")  # video_key still optional
    try:
        therapist = User(clerk_id="user_t", email="t@example.com", role=Role.THERAPIST)
        patient = User(clerk_id="user_p", email="p@example.com", role=Role.PATIENT)
        db.add_all([therapist, patient])
        db.flush()
        squat = db.scalars(select(Exercise).where(Exercise.name == "squat")).one()
        plan = Plan(therapist_id=therapist.id, patient_id=patient.id)
        target = PlanExercise(
            plan=plan, exercise=squat, reps=10, sets=3, times_per_week=3
        )
        db.add(ExerciseSession(plan_exercise=target, status="processing"))
        db.commit()
        db.close()  # no open transaction may block the migration's ALTER TABLE

        with pytest.raises(IntegrityError, match="contains null values"):
            command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            revision = MigrationContext.configure(connection).get_current_revision()
            keyless = connection.scalar(
                select(func.count())
                .select_from(ExerciseSession)
                .where(ExerciseSession.video_key.is_(None))
            )
        assert (revision, keyless) == ("e846d97b14af", 1)
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(ExerciseSession).where(ExerciseSession.video_key.is_(None))
            )
        command.upgrade(alembic_config, "head")
