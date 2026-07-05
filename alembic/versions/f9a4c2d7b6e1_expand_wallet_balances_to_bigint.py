"""expand wallet balances to bigint

Revision ID: f9a4c2d7b6e1
Revises: e3c1f4a8b902
Create Date: 2026-04-08 20:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f9a4c2d7b6e1"
down_revision: Union[str, None] = "e3c1f4a8b902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "wallet_balance",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="wallet_balance::bigint",
    )
    op.alter_column(
        "units",
        "wallet_balance",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="wallet_balance::bigint",
    )


def downgrade() -> None:
    op.alter_column(
        "units",
        "wallet_balance",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
        postgresql_using="wallet_balance::integer",
    )
    op.alter_column(
        "users",
        "wallet_balance",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
        postgresql_using="wallet_balance::integer",
    )
