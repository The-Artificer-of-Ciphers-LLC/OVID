"""add unique constraint on disc_set_id + disc_number

Revision ID: 900000000004
Revises: 900000000002
Create Date: 2026-04-04 18:25:00.000000

Enforces that no two discs in the same set can have the same disc_number.
NULL disc_set_id values are excluded from uniqueness by SQL standard.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '900000000004'
down_revision: Union[str, None] = '900000000003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_disc_set_disc_number", "discs", ["disc_set_id", "disc_number"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_disc_set_disc_number", "discs")
