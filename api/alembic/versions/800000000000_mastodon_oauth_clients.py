"""mastodon oauth clients

Revision ID: 800000000000
Revises: 7ffb31fc807f
Create Date: 2026-04-03 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '800000000000'
down_revision: Union[str, None] = '7ffb31fc807f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('mastodon_oauth_clients',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('domain', sa.String(length=255), nullable=False),
    sa.Column('client_id', sa.String(length=255), nullable=False),
    sa.Column('client_secret', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('domain')
    )


def downgrade() -> None:
    op.drop_table('mastodon_oauth_clients')
