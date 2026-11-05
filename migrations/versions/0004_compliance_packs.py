"""compliance packs: letter, checks and summary

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"

KINDS_BEFORE = "'agreement', 'deliverable', 'correspondence', 'id', 'other', 'payer_confirmation'"
KINDS_AFTER = KINDS_BEFORE + ", 'pack'"


def upgrade() -> None:
    op.add_column("packs", sa.Column("letter", sa.Text(), nullable=False, server_default=""))
    op.add_column(
        "packs",
        sa.Column("letter_source", sa.String(10), nullable=False, server_default="standard"),
    )
    op.add_column(
        "packs",
        sa.Column("summary", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column("packs", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "letter_source_allowed", "packs", "letter_source IN ('ai', 'standard', 'edited')"
    )
    op.create_index("ix_packs_user_created", "packs", ["user_id", "created_at"])
    op.drop_constraint("kind_allowed", "documents", type_="check")
    op.create_check_constraint("kind_allowed", "documents", f"kind IN ({KINDS_AFTER})")


def downgrade() -> None:
    op.execute("UPDATE packs SET pdf_document_id = NULL, zip_document_id = NULL")
    op.execute("DELETE FROM documents WHERE kind = 'pack'")
    op.drop_constraint("kind_allowed", "documents", type_="check")
    op.create_check_constraint("kind_allowed", "documents", f"kind IN ({KINDS_BEFORE})")
    op.drop_index("ix_packs_user_created", "packs")
    op.drop_constraint("letter_source_allowed", "packs", type_="check")
    for column in ("updated_at", "summary", "letter_source", "letter"):
        op.drop_column("packs", column)
