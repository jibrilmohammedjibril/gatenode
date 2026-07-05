"""remove legacy payment schema

Revision ID: c2a8f6d4e901
Revises: 9b1c2d3e4f5a
Create Date: 2026-03-24 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2a8f6d4e901"
down_revision: Union[str, None] = "9b1c2d3e4f5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(inspector: sa.Inspector) -> set[str]:
    return set(inspector.get_table_names())


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = _table_names(inspector)

    if "units" in tables:
        unit_columns = _column_names(inspector, "units")
        for column_name in ("virtual_account_name", "virtual_account_number", "virtual_account_bank"):
            if column_name in unit_columns:
                op.drop_column("units", column_name)

    if "bank_transfer_references" in tables:
        transfer_columns = _column_names(inspector, "bank_transfer_references")
        if "paystack_customer_code" in transfer_columns:
            op.drop_column("bank_transfer_references", "paystack_customer_code")

    if "saved_cards" in tables:
        saved_card_indexes = _index_names(inspector, "saved_cards")
        if "ix_saved_cards_user_id" in saved_card_indexes:
            op.drop_index("ix_saved_cards_user_id", table_name="saved_cards")
        op.drop_table("saved_cards")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = _table_names(inspector)

    if "units" in tables:
        unit_columns = _column_names(inspector, "units")
        if "virtual_account_bank" not in unit_columns:
            op.add_column("units", sa.Column("virtual_account_bank", sa.String(), nullable=True))
        if "virtual_account_number" not in unit_columns:
            op.add_column("units", sa.Column("virtual_account_number", sa.String(), nullable=True))
        if "virtual_account_name" not in unit_columns:
            op.add_column("units", sa.Column("virtual_account_name", sa.String(), nullable=True))

    if "bank_transfer_references" in tables:
        transfer_columns = _column_names(inspector, "bank_transfer_references")
        if "paystack_customer_code" not in transfer_columns:
            op.add_column("bank_transfer_references", sa.Column("paystack_customer_code", sa.String(), nullable=True))

    if "saved_cards" not in tables:
        op.create_table(
            "saved_cards",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("authorization_code", sa.String(), nullable=False),
            sa.Column("last4", sa.String(), nullable=False),
            sa.Column("brand", sa.String(), nullable=False),
            sa.Column("exp_month", sa.String(), nullable=False),
            sa.Column("exp_year", sa.String(), nullable=False),
            sa.Column("bin", sa.String(), nullable=True),
            sa.Column("bank", sa.String(), nullable=True),
            sa.Column("channel", sa.String(), nullable=True),
            sa.Column("signature", sa.String(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_saved_cards_user_id"), "saved_cards", ["user_id"], unique=False)
