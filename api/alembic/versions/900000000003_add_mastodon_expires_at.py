"""Add expires_at to mastodon_oauth_clients.

Revision ID: 900000000003
Revises: 900000000002
Create Date: 2026-04-04

Existing rows get NULL, which is treated as expired on next lookup
(lazy re-registration).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "900000000003"
down_revision = "900000000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mastodon_oauth_clients",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mastodon_oauth_clients", "expires_at")
