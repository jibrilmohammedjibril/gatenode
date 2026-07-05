"""add mono bvn sessions

Revision ID: c6f4b2780e21
Revises: a41d9f7c2e10
Create Date: 2026-04-18 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c6f4b2780e21"
down_revision: Union[str, None] = "a41d9f7c2e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "mono_bvn_sessions" not in tables:
        op.create_table(
            "mono_bvn_sessions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("provider", sa.String(), nullable=False, server_default="mono"),
            sa.Column("reference", sa.String(), nullable=False),
            sa.Column("mono_session_id", sa.String(), nullable=False),
            sa.Column("bvn_last4", sa.String(), nullable=True),
            sa.Column("selected_method", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="initiated"),
            sa.Column("identity_payload", sa.JSON(), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("reference"),
        )
        op.create_index(op.f("ix_mono_bvn_sessions_user_id"), "mono_bvn_sessions", ["user_id"], unique=False)
        op.create_index(op.f("ix_mono_bvn_sessions_reference"), "mono_bvn_sessions", ["reference"], unique=False)
        op.create_index(op.f("ix_mono_bvn_sessions_mono_session_id"), "mono_bvn_sessions", ["mono_session_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "mono_bvn_sessions" in tables:
        indexes = {index["name"] for index in inspector.get_indexes("mono_bvn_sessions")}
        for index_name in (
            op.f("ix_mono_bvn_sessions_mono_session_id"),
            op.f("ix_mono_bvn_sessions_reference"),
            op.f("ix_mono_bvn_sessions_user_id"),
        ):
            if index_name in indexes:
                op.drop_index(index_name, table_name="mono_bvn_sessions")
        op.drop_table("mono_bvn_sessions")
