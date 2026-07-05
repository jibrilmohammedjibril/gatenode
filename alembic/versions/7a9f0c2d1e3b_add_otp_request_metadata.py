"""add otp request metadata

Revision ID: 7a9f0c2d1e3b
Revises: 6f0e2f8a6c41
Create Date: 2026-06-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7a9f0c2d1e3b"
down_revision: Union[str, None] = "6f0e2f8a6c41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("otp_codes", sa.Column("request_ip", sa.String(), nullable=True))
    op.add_column("otp_codes", sa.Column("request_user_agent", sa.Text(), nullable=True))
    op.add_column("otp_codes", sa.Column("request_path", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("otp_codes", "request_path")
    op.drop_column("otp_codes", "request_user_agent")
    op.drop_column("otp_codes", "request_ip")
