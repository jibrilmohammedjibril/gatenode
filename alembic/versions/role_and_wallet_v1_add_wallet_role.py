"""add user wallet and role

Revision ID: role_and_wallet_v1
Revises: abc123def456
Create Date: 2026-01-30 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'role_and_wallet_v1'
down_revision = 'abc123def456'
branch_labels = None
depends_on = None

def upgrade():
    # 1. Create Enum Type (Safe check if exists, but assuming it doesn't)
    # We use a raw execute to avoid errors if it exists, or just try/except block in python?
    # Better to just let it create.
    householdrole = postgresql.ENUM('ADMIN', 'SPOUSE', 'CHILD', 'PARENT', 'RELATIVE', 'STAFF', 'OTHER', name='householdrole')
    try:
        householdrole.create(op.get_bind())
    except Exception:
        pass # Might exist already? Unlikely.

    # 2. Add wallet_balance to users
    op.add_column('users', sa.Column('wallet_balance', sa.Integer(), server_default='0', nullable=True))
    
    # 3. Add role to user_units
    # We use the enum object we created or reference by name
    op.add_column('user_units', sa.Column('role', sa.Enum('ADMIN', 'SPOUSE', 'CHILD', 'PARENT', 'RELATIVE', 'STAFF', 'OTHER', name='householdrole'), nullable=True))
    
    # Set default role to OTHER for existing rows (optional but good)
    op.execute("UPDATE user_units SET role = 'OTHER' WHERE role IS NULL")


def downgrade():
    op.drop_column('user_units', 'role')
    op.drop_column('users', 'wallet_balance')
    op.execute("DROP TYPE householdrole")
