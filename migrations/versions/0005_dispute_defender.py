"""dispute defender: lifecycle, draft response, approval and submission

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    columns = [
        sa.Column("stage", sa.String(32)),
        sa.Column("source", sa.String(10), nullable=False, server_default="webhook"),
        sa.Column("allowed", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("buyer_messages", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("response", sa.Text()),
        sa.Column("response_source", sa.String(10)),
        sa.Column("rejected", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("approval_token_hash", sa.String(64), unique=True),
        sa.Column("approval_expires_at", sa.DateTime(timezone=True)),
        sa.Column("draft_hash", sa.String(64)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("submission", postgresql.JSONB()),
        sa.Column("refreshed_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    ]
    for column in columns:
        op.add_column("disputes", column)
    op.create_check_constraint("source_allowed", "disputes", "source IN ('webhook', 'seed')")
    op.create_check_constraint(
        "response_source_allowed",
        "disputes",
        "response_source IS NULL OR response_source IN ('ai', 'standard', 'edited')",
    )


def downgrade() -> None:
    op.drop_constraint("response_source_allowed", "disputes", type_="check")
    op.drop_constraint("source_allowed", "disputes", type_="check")
    for name in (
        "resolved_at",
        "refreshed_at",
        "submission",
        "submitted_at",
        "draft_hash",
        "approval_expires_at",
        "approval_token_hash",
        "rejected",
        "response_source",
        "response",
        "buyer_messages",
        "allowed",
        "source",
        "stage",
    ):
        op.drop_column("disputes", name)
