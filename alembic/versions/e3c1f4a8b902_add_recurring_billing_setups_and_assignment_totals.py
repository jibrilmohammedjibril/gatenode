"""add recurring billing setups and assignment totals

Revision ID: e3c1f4a8b902
Revises: b7e1c0a9d4f2
Create Date: 2026-04-06 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e3c1f4a8b902"
down_revision: Union[str, None] = "b7e1c0a9d4f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


billgenerationsource = sa.Enum(
    "manual",
    "recurring",
    name="billgenerationsource",
)

billgenerationsource_column = postgresql.ENUM(
    "manual",
    "recurring",
    name="billgenerationsource",
    create_type=False,
)

recurringbillingduration = sa.Enum(
    "monthly",
    "bi_monthly",
    "quarterly",
    "half_yearly",
    "yearly",
    name="recurringbillingduration",
)

recurringbillingduration_column = postgresql.ENUM(
    "monthly",
    "bi_monthly",
    "quarterly",
    "half_yearly",
    "yearly",
    name="recurringbillingduration",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    billgenerationsource.create(bind, checkfirst=True)
    recurringbillingduration.create(bind, checkfirst=True)

    op.create_table(
        "recurring_billing_setups",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("estate_id", sa.String(), nullable=False),
        sa.Column("bill_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("base_amount", sa.Integer(), nullable=True),
        sa.Column("duration", recurringbillingduration_column, nullable=False),
        sa.Column("first_due_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_due_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("auto_renew", sa.Boolean(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["estate_id"], ["estates.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("estate_id", "bill_type", name="uq_recurring_billing_setup_estate_type"),
    )
    op.create_index(op.f("ix_recurring_billing_setups_estate_id"), "recurring_billing_setups", ["estate_id"], unique=False)

    op.add_column(
        "bills",
        sa.Column("generation_source", billgenerationsource_column, server_default="manual", nullable=False),
    )
    op.add_column("bills", sa.Column("recurring_setup_id", sa.String(), nullable=True))
    op.add_column("bills", sa.Column("cycle_due_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bills", sa.Column("is_variable_amount", sa.Boolean(), server_default=sa.text("false"), nullable=True))
    op.create_index(op.f("ix_bills_recurring_setup_id"), "bills", ["recurring_setup_id"], unique=False)
    op.create_unique_constraint(
        "uq_bills_recurring_setup_cycle",
        "bills",
        ["recurring_setup_id", "cycle_due_date"],
    )
    op.create_foreign_key(
        "fk_bills_recurring_setup_id",
        "bills",
        "recurring_billing_setups",
        ["recurring_setup_id"],
        ["id"],
    )

    op.add_column("bill_assignments", sa.Column("base_amount", sa.Integer(), nullable=True))
    op.add_column("bill_assignments", sa.Column("app_charge_amount", sa.Integer(), nullable=True))
    op.add_column("bill_assignments", sa.Column("total_amount", sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE bill_assignments
        SET
            base_amount = bills.total_amount,
            app_charge_amount = 0,
            total_amount = bills.total_amount
        FROM bills
        WHERE bill_assignments.bill_id = bills.id
          AND bill_assignments.total_amount IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("bill_assignments", "total_amount")
    op.drop_column("bill_assignments", "app_charge_amount")
    op.drop_column("bill_assignments", "base_amount")

    op.drop_constraint("fk_bills_recurring_setup_id", "bills", type_="foreignkey")
    op.drop_constraint("uq_bills_recurring_setup_cycle", "bills", type_="unique")
    op.drop_index(op.f("ix_bills_recurring_setup_id"), table_name="bills")
    op.drop_column("bills", "is_variable_amount")
    op.drop_column("bills", "cycle_due_date")
    op.drop_column("bills", "recurring_setup_id")
    op.drop_column("bills", "generation_source")

    op.drop_index(op.f("ix_recurring_billing_setups_estate_id"), table_name="recurring_billing_setups")
    op.drop_table("recurring_billing_setups")

    recurringbillingduration.drop(op.get_bind(), checkfirst=True)
    billgenerationsource.drop(op.get_bind(), checkfirst=True)
