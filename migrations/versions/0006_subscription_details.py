"""subscription details for Kweli Pro

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("next_billing_at", sa.DateTime(timezone=True)))
    op.add_column("subscriptions", sa.Column("updated_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("subscriptions", "updated_at")
    op.drop_column("subscriptions", "next_billing_at")
