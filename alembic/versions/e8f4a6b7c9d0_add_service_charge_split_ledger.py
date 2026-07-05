"""add service charge split ledger

Revision ID: e8f4a6b7c9d0
Revises: 7a9f0c2d1e3b, a7b4c9d1e2f3, c9f1d2e3a4b5
Create Date: 2026-06-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8f4a6b7c9d0"
down_revision: Union[str, tuple[str, ...], None] = (
    "7a9f0c2d1e3b",
    "a7b4c9d1e2f3",
    "c9f1d2e3a4b5",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bill_assignments", sa.Column("service_fee_amount", sa.Integer(), nullable=True))
    op.add_column("bill_assignments", sa.Column("resident_service_fee_amount", sa.Integer(), nullable=True))
    op.add_column("bill_assignments", sa.Column("estate_absorbed_service_fee_amount", sa.Integer(), nullable=True))
    op.add_column("bill_assignments", sa.Column("estate_net_amount", sa.Integer(), nullable=True))
    op.add_column("payouts", sa.Column("amount_kobo", sa.Integer(), nullable=True))

    op.create_table(
        "service_charge_fee_configs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("estate_id", sa.String(), nullable=True),
        sa.Column("monthly_fee_amount", sa.Integer(), nullable=False, server_default="100000"),
        sa.Column("discount_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("allocation_mode", sa.String(), nullable=False, server_default="resident_pays_all"),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["estate_id"], ["estates.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("estate_id", name="uq_service_charge_fee_config_estate"),
    )
    op.create_index(op.f("ix_service_charge_fee_configs_estate_id"), "service_charge_fee_configs", ["estate_id"], unique=False)

    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=True),
        sa.Column("bill_assignment_id", sa.String(), nullable=False),
        sa.Column("bill_id", sa.String(), nullable=False),
        sa.Column("estate_id", sa.String(), nullable=False),
        sa.Column("unit_id", sa.String(), nullable=False),
        sa.Column("gross_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("service_fee_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estate_net_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("allocation_status", sa.String(), nullable=False, server_default="pending_transfer"),
        sa.Column("allocation_source", sa.String(), nullable=False, server_default="service_charge_payment"),
        sa.Column("payment_reference", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["bill_assignment_id"], ["bill_assignments.id"]),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"]),
        sa.ForeignKeyConstraint(["estate_id"], ["estates.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_allocations_transaction_id"), "payment_allocations", ["transaction_id"], unique=False)
    op.create_index(op.f("ix_payment_allocations_bill_assignment_id"), "payment_allocations", ["bill_assignment_id"], unique=False)
    op.create_index(op.f("ix_payment_allocations_bill_id"), "payment_allocations", ["bill_id"], unique=False)
    op.create_index(op.f("ix_payment_allocations_estate_id"), "payment_allocations", ["estate_id"], unique=False)
    op.create_index(op.f("ix_payment_allocations_unit_id"), "payment_allocations", ["unit_id"], unique=False)
    op.create_index(op.f("ix_payment_allocations_payment_reference"), "payment_allocations", ["payment_reference"], unique=False)

    op.create_table(
        "service_charge_split_transfers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=True),
        sa.Column("transfer_kind", sa.String(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_account_id", sa.String(), nullable=True),
        sa.Column("destination_account_id", sa.String(), nullable=False),
        sa.Column("provider_reference", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("request_payload", sa.JSON(), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_service_charge_split_transfer_idempotency_key"),
    )
    op.create_index(op.f("ix_service_charge_split_transfers_transaction_id"), "service_charge_split_transfers", ["transaction_id"], unique=False)
    op.create_index(op.f("ix_service_charge_split_transfers_provider_reference"), "service_charge_split_transfers", ["provider_reference"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_service_charge_split_transfers_provider_reference"), table_name="service_charge_split_transfers")
    op.drop_index(op.f("ix_service_charge_split_transfers_transaction_id"), table_name="service_charge_split_transfers")
    op.drop_table("service_charge_split_transfers")

    op.drop_index(op.f("ix_payment_allocations_payment_reference"), table_name="payment_allocations")
    op.drop_index(op.f("ix_payment_allocations_unit_id"), table_name="payment_allocations")
    op.drop_index(op.f("ix_payment_allocations_estate_id"), table_name="payment_allocations")
    op.drop_index(op.f("ix_payment_allocations_bill_id"), table_name="payment_allocations")
    op.drop_index(op.f("ix_payment_allocations_bill_assignment_id"), table_name="payment_allocations")
    op.drop_index(op.f("ix_payment_allocations_transaction_id"), table_name="payment_allocations")
    op.drop_table("payment_allocations")

    op.drop_index(op.f("ix_service_charge_fee_configs_estate_id"), table_name="service_charge_fee_configs")
    op.drop_table("service_charge_fee_configs")

    op.drop_column("payouts", "amount_kobo")
    op.drop_column("bill_assignments", "estate_net_amount")
    op.drop_column("bill_assignments", "estate_absorbed_service_fee_amount")
    op.drop_column("bill_assignments", "resident_service_fee_amount")
    op.drop_column("bill_assignments", "service_fee_amount")
