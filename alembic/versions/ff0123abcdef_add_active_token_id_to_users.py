"""add active_token_id to users

Revision ID: ff0123abcdef
Revises: f2df0776510e
Create Date: 2026-01-27 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ff0123abcdef'
down_revision = '849266eb7f47' # Rebased to latest head
branch_labels = None
depends_on = None


def upgrade():
    # Add active_token_id to users table
    op.add_column('users', sa.Column('active_token_id', sa.String(), nullable=True))


def downgrade():
    # Remove active_token_id from users table
    op.drop_column('users', 'active_token_id')
