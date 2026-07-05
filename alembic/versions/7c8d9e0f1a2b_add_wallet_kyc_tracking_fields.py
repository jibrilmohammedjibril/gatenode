"""add wallet kyc tracking fields

Revision ID: 7c8d9e0f1a2b
Revises: c1f3e6b4a9d2
Create Date: 2026-03-21 17:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c8d9e0f1a2b"
down_revision: Union[str, None] = "c1f3e6b4a9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("wallet_profiles")}

    if "kyc_message" not in columns:
        op.add_column("wallet_profiles", sa.Column("kyc_message", sa.Text(), nullable=True))

    if "kyc_requirements" not in columns:
        op.add_column("wallet_profiles", sa.Column("kyc_requirements", sa.JSON(), nullable=True))

    if "kyc_last_event" not in columns:
        op.add_column("wallet_profiles", sa.Column("kyc_last_event", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("wallet_profiles")}

    if "kyc_last_event" in columns:
        op.drop_column("wallet_profiles", "kyc_last_event")

    if "kyc_requirements" in columns:
        op.drop_column("wallet_profiles", "kyc_requirements")

    if "kyc_message" in columns:
        op.drop_column("wallet_profiles", "kyc_message")
