"""Switch from Anchor to Nomba and remove Mono

Revision ID: c13058d8c468
Revises: f3b2c4d5e6a7
Create Date: 2026-07-04 13:15:49.077990

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c13058d8c468'
down_revision: Union[str, None] = 'f3b2c4d5e6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update wallet_profiles
    op.add_column('wallet_profiles', sa.Column('nomba_account_ref', sa.String(), nullable=True))
    op.add_column('wallet_profiles', sa.Column('nomba_account_id', sa.String(), nullable=True))
    op.create_unique_constraint(None, 'wallet_profiles', ['nomba_account_ref'])
    op.create_unique_constraint(None, 'wallet_profiles', ['nomba_account_id'])
    
    op.drop_constraint('wallet_profiles_anchor_customer_id_key', 'wallet_profiles', type_='unique')
    op.drop_constraint('wallet_profiles_anchor_account_id_key', 'wallet_profiles', type_='unique')
    op.drop_column('wallet_profiles', 'anchor_customer_id')
    op.drop_column('wallet_profiles', 'anchor_account_id')

    # 2. Update kyc_sessions
    op.add_column('kyc_sessions', sa.Column('nomba_account_ref', sa.String(), nullable=False, server_default=''))
    op.drop_column('kyc_sessions', 'anchor_customer_id')

    # 3. Drop mono_bvn_sessions table
    op.drop_index('ix_mono_bvn_sessions_reference', table_name='mono_bvn_sessions')
    op.drop_index('ix_mono_bvn_sessions_mono_session_id', table_name='mono_bvn_sessions')
    op.drop_index('ix_mono_bvn_sessions_user_id', table_name='mono_bvn_sessions')
    op.drop_table('mono_bvn_sessions')


def downgrade() -> None:
    pass
