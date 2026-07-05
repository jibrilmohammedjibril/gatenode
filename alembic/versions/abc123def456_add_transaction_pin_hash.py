"""add transaction_pin_hash to users

Revision ID: abc123def456
Revises: ff0123abcdef
Create Date: 2026-01-28 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'abc123def456'
down_revision = 'ff0123abcdef'
branch_labels = None
depends_on = None


def upgrade():
    # Add transaction_pin_hash to users table
    op.add_column('users', sa.Column('transaction_pin_hash', sa.String(), nullable=True))


def downgrade():
    # Remove transaction_pin_hash from users table
    op.drop_column('users', 'transaction_pin_hash')
