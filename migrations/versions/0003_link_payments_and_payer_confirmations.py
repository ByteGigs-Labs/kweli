"""link payments to agreements, payer confirmations

A payment that didn't come through a Kweli invoice can be linked to its agreement by hand, and
a client's written confirmation of a third-party payment can be stored with the agreement.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"

KINDS_BEFORE = "'agreement', 'deliverable', 'correspondence', 'id', 'other'"
KINDS_AFTER = KINDS_BEFORE + ", 'payer_confirmation'"


def upgrade() -> None:
    op.add_column("payments", sa.Column("agreement_id", sa.UUID(), nullable=True))
    op.create_index("ix_payments_agreement_id", "payments", ["agreement_id"])
    op.create_foreign_key(
        "payments_agreement_id_fkey",
        "payments",
        "agreements",
        ["agreement_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("kind_allowed", "documents", type_="check")
    op.create_check_constraint("kind_allowed", "documents", f"kind IN ({KINDS_AFTER})")


def downgrade() -> None:
    op.execute("DELETE FROM documents WHERE kind = 'payer_confirmation'")
    op.drop_constraint("kind_allowed", "documents", type_="check")
    op.create_check_constraint("kind_allowed", "documents", f"kind IN ({KINDS_BEFORE})")
    op.drop_constraint("payments_agreement_id_fkey", "payments", type_="foreignkey")
    op.drop_index("ix_payments_agreement_id", "payments")
    op.drop_column("payments", "agreement_id")
