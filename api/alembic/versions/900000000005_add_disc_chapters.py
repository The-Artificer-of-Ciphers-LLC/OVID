"""add disc_chapters table for chapter metadata

Revision ID: 900000000005
Revises: 900000000004
Create Date: 2026-04-04 20:30:00.000000

Adds per-title chapter data: index, optional name (max 200 chars),
and optional start_time_secs (integer seconds).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '900000000005'
down_revision: Union[str, None] = '900000000004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "disc_chapters",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "disc_title_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("disc_titles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chapter_index", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("start_time_secs", sa.Integer(), nullable=True),
        sa.UniqueConstraint("disc_title_id", "chapter_index", name="uq_disc_chapters_index"),
    )
    op.create_index("idx_disc_chapters_title", "disc_chapters", ["disc_title_id"])


def downgrade() -> None:
    op.drop_index("idx_disc_chapters_title", table_name="disc_chapters")
    op.drop_table("disc_chapters")
