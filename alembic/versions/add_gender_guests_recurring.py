"""Add gender expected_guests and recurring invite type

Revision ID: add_gender_guests_recurring
Revises: f516cac80eec
Create Date: 2026-02-14 11:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_gender_guests_recurring'
down_revision = 'f516cac80eec'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Add columns
    op.add_column('visitor_invites', sa.Column('gender', sa.String(), nullable=True))
    op.add_column('visitor_invites', sa.Column('expected_guests', sa.Integer(), nullable=True))
    
    # Update Enum (Postgres requires explicit ALTER TYPE for Enums)
    # invite_type enum
    op.execute("ALTER TYPE invitetype ADD VALUE IF NOT EXISTS 'recurring'")

def downgrade() -> None:
    op.drop_column('visitor_invites', 'expected_guests')
    op.drop_column('visitor_invites', 'gender')
    # Enum rollback is tricky in Postgres, usually ignored or requires creating new type
