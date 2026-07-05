"""add_active_token_id_to_device_tokens

Revision ID: 6716c5db54d6
Revises: 9132e657adc3
Create Date: 2026-02-18 16:55:47.552700

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6716c5db54d6'
down_revision: Union[str, None] = '9132e657adc3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("device_tokens")}
    if "active_token_id" not in columns:
        op.add_column('device_tokens', sa.Column('active_token_id', sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("device_tokens")}
    if "active_token_id" in columns:
        op.drop_column('device_tokens', 'active_token_id')
