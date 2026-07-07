"""pending account links

Revision ID: 900000000007
Revises: 900000000006
Create Date: 2026-07-07 02:26:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '900000000007'
down_revision: Union[str, None] = '900000000006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('pending_account_links',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('existing_user_id', sa.UUID(), nullable=False),
    sa.Column('new_provider', sa.String(length=30), nullable=False),
    sa.Column('new_provider_id', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['existing_user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_pending_account_links_existing_user', 'pending_account_links', ['existing_user_id'])


def downgrade() -> None:
    op.drop_index('idx_pending_account_links_existing_user', table_name='pending_account_links')
    op.drop_table('pending_account_links')
