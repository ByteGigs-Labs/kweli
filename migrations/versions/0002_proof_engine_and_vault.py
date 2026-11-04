"""proof engine and vault

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.create_table(
        "document_blobs",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(length=12), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id"),
    )

    op.add_column("documents", sa.Column("agreement_id", sa.UUID(), nullable=True))
    op.create_index("ix_documents_agreement_id", "documents", ["agreement_id"])
    op.create_foreign_key(
        "documents_agreement_id_fkey",
        "documents",
        "agreements",
        ["agreement_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "payments", sa.Column("payer_resolved_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.alter_column(
        "proof_flags",
        "status",
        existing_type=sa.VARCHAR(length=4),
        type_=sa.String(length=7),
        existing_nullable=False,
    )
    op.drop_constraint("status_allowed", "proof_flags", type_="check")
    op.create_check_constraint(
        "status_allowed", "proof_flags", "status IN ('pass', 'warn', 'fail', 'pending')"
    )

    op.add_column("users", sa.Column("paypal_merchant_id", sa.String(length=32), nullable=True))
    op.create_unique_constraint("users_paypal_merchant_id_key", "users", ["paypal_merchant_id"])

    op.add_column("webhook_events", sa.Column("resource_id", sa.String(length=64)))
    op.add_column(
        "webhook_events",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("webhook_events", sa.Column("note", sa.String(length=300)))
    op.create_check_constraint(
        "status_allowed",
        "webhook_events",
        "status IN ('received', 'processed', 'ignored', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint("status_allowed", "webhook_events", type_="check")
    op.drop_column("webhook_events", "note")
    op.drop_column("webhook_events", "attempts")
    op.drop_column("webhook_events", "resource_id")
    op.drop_constraint("users_paypal_merchant_id_key", "users", type_="unique")
    op.drop_column("users", "paypal_merchant_id")
    op.execute("DELETE FROM proof_flags WHERE status = 'pending'")
    op.drop_constraint("status_allowed", "proof_flags", type_="check")
    op.create_check_constraint(
        "status_allowed", "proof_flags", "status IN ('pass', 'warn', 'fail')"
    )
    op.alter_column(
        "proof_flags",
        "status",
        existing_type=sa.String(length=7),
        type_=sa.VARCHAR(length=4),
        existing_nullable=False,
    )
    op.drop_column("payments", "payer_resolved_at")
    op.drop_constraint("documents_agreement_id_fkey", "documents", type_="foreignkey")
    op.drop_index("ix_documents_agreement_id", table_name="documents")
    op.drop_column("documents", "agreement_id")
    op.drop_table("document_blobs")
