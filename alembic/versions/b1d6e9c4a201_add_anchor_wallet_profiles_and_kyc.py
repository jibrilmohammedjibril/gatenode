"""Add Anchor wallet profiles and KYC session state

Revision ID: b1d6e9c4a201
Revises: 6716c5db54d6
Create Date: 2026-02-28 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1d6e9c4a201"
down_revision: Union[str, None] = "6716c5db54d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("gender", sa.String(), nullable=True))

    op.create_table(
        "wallet_profiles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("anchor_customer_id", sa.String(), nullable=True),
        sa.Column("anchor_account_id", sa.String(), nullable=True),
        sa.Column("bank_name", sa.String(), nullable=True),
        sa.Column("account_number", sa.String(), nullable=True),
        sa.Column("account_name", sa.String(), nullable=True),
        sa.Column("verification_reference", sa.String(), nullable=True),
        sa.Column("kyc_tier", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("anchor_account_id"),
        sa.UniqueConstraint("anchor_customer_id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_wallet_profiles_user_id"), "wallet_profiles", ["user_id"], unique=True)
    op.create_index(
        op.f("ix_wallet_profiles_verification_reference"),
        "wallet_profiles",
        ["verification_reference"],
        unique=False,
    )

    op.create_table(
        "kyc_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("reference", sa.String(), nullable=False),
        sa.Column("anchor_customer_id", sa.String(), nullable=False),
        sa.Column("bvn_last4", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference"),
    )
    op.create_index(op.f("ix_kyc_sessions_reference"), "kyc_sessions", ["reference"], unique=True)
    op.create_index(op.f("ix_kyc_sessions_user_id"), "kyc_sessions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_kyc_sessions_user_id"), table_name="kyc_sessions")
    op.drop_index(op.f("ix_kyc_sessions_reference"), table_name="kyc_sessions")
    op.drop_table("kyc_sessions")

    op.drop_index(op.f("ix_wallet_profiles_verification_reference"), table_name="wallet_profiles")
    op.drop_index(op.f("ix_wallet_profiles_user_id"), table_name="wallet_profiles")
    op.drop_table("wallet_profiles")

    op.drop_column("users", "gender")
    op.drop_column("users", "date_of_birth")
