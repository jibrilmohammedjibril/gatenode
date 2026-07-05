"""add superadmin payout tracking

Revision ID: a7b4c9d1e2f3
Revises: 65bc43debfc4, add_gender_guests_recurring, role_and_wallet_v1
Create Date: 2026-04-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7b4c9d1e2f3"
down_revision: Union[str, tuple[str, ...], None] = (
    "65bc43debfc4",
    "add_gender_guests_recurring",
    "role_and_wallet_v1",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payouts", sa.Column("requested_by_user_id", sa.String(), nullable=True))
    op.add_column("payouts", sa.Column("processed_by_user_id", sa.String(), nullable=True))
    op.add_column("payouts", sa.Column("bank_name_snapshot", sa.String(), nullable=True))
    op.add_column("payouts", sa.Column("account_number_snapshot", sa.String(), nullable=True))
    op.add_column("payouts", sa.Column("account_name_snapshot", sa.String(), nullable=True))
    op.add_column("payouts", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payouts", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payouts", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payouts", sa.Column("transfer_reference", sa.String(), nullable=True))
    op.add_column("payouts", sa.Column("failure_reason", sa.Text(), nullable=True))
    op.add_column("payouts", sa.Column("internal_note", sa.Text(), nullable=True))

    op.create_index(op.f("ix_payouts_requested_by_user_id"), "payouts", ["requested_by_user_id"], unique=False)
    op.create_index(op.f("ix_payouts_processed_by_user_id"), "payouts", ["processed_by_user_id"], unique=False)
    op.create_index(op.f("ix_payouts_transfer_reference"), "payouts", ["transfer_reference"], unique=False)
    op.create_foreign_key(
        "fk_payouts_requested_by_user_id_users",
        "payouts",
        "users",
        ["requested_by_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_payouts_processed_by_user_id_users",
        "payouts",
        "users",
        ["processed_by_user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_payouts_processed_by_user_id_users", "payouts", type_="foreignkey")
    op.drop_constraint("fk_payouts_requested_by_user_id_users", "payouts", type_="foreignkey")
    op.drop_index(op.f("ix_payouts_transfer_reference"), table_name="payouts")
    op.drop_index(op.f("ix_payouts_processed_by_user_id"), table_name="payouts")
    op.drop_index(op.f("ix_payouts_requested_by_user_id"), table_name="payouts")

    op.drop_column("payouts", "internal_note")
    op.drop_column("payouts", "failure_reason")
    op.drop_column("payouts", "transfer_reference")
    op.drop_column("payouts", "failed_at")
    op.drop_column("payouts", "paid_at")
    op.drop_column("payouts", "processing_started_at")
    op.drop_column("payouts", "account_name_snapshot")
    op.drop_column("payouts", "account_number_snapshot")
    op.drop_column("payouts", "bank_name_snapshot")
    op.drop_column("payouts", "processed_by_user_id")
    op.drop_column("payouts", "requested_by_user_id")
