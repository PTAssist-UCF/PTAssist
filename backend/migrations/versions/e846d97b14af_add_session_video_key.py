"""Add the private video key used by upload and background analysis.

Revision ID: e846d97b14af
Revises: c35bebbdd455
"""

import sqlalchemy as sa
from alembic import op

revision: str = "e846d97b14af"
down_revision: str | None = "c35bebbdd455"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("video_key", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_sessions_video_key", "sessions", ["video_key"])


def downgrade() -> None:
    op.drop_constraint("uq_sessions_video_key", "sessions", type_="unique")
    op.drop_column("sessions", "video_key")
