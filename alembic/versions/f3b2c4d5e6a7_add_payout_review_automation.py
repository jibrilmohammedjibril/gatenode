"""add payout review automation

Revision ID: f3b2c4d5e6a7
Revises: e8f4a6b7c9d0
Create Date: 2026-06-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3b2c4d5e6a7"
down_revision: Union[str, None] = "e8f4a6b7c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payouts", sa.Column("blocked_by_user_id", sa.String(), nullable=True))
    op.add_column("payouts", sa.Column("bank_code_snapshot", sa.String(), nullable=True))
    op.add_column("payouts", sa.Column("review_deadline_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payouts", sa.Column("auto_process_after", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payouts", sa.Column("auto_process_enabled", sa.Boolean(), nullable=True, server_default=sa.text("true")))
    op.add_column("payouts", sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payouts", sa.Column("block_reason", sa.Text(), nullable=True))
    op.add_column("payouts", sa.Column("transfer_response_payload", sa.JSON(), nullable=True))

    op.create_index(op.f("ix_payouts_blocked_by_user_id"), "payouts", ["blocked_by_user_id"], unique=False)
    op.create_foreign_key(
        "fk_payouts_blocked_by_user_id_users",
        "payouts",
        "users",
        ["blocked_by_user_id"],
        ["id"],
    )
    op.create_index(op.f("ix_payouts_auto_process_after"), "payouts", ["auto_process_after"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payouts_auto_process_after"), table_name="payouts")
    op.drop_constraint("fk_payouts_blocked_by_user_id_users", "payouts", type_="foreignkey")
    op.drop_index(op.f("ix_payouts_blocked_by_user_id"), table_name="payouts")

    op.drop_column("payouts", "transfer_response_payload")
    op.drop_column("payouts", "block_reason")
    op.drop_column("payouts", "blocked_at")
    op.drop_column("payouts", "auto_process_enabled")
    op.drop_column("payouts", "auto_process_after")
    op.drop_column("payouts", "review_deadline_at")
    op.drop_column("payouts", "bank_code_snapshot")
    op.drop_column("payouts", "blocked_by_user_id")
