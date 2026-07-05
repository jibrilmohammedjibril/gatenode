"""Add feed messaging performance indexes

Revision ID: a4f9c2b7d1e3
Revises: c2a8f6d4e901
Create Date: 2026-03-27 09:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a4f9c2b7d1e3"
down_revision: Union[str, None] = "c2a8f6d4e901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_feed_messages_conversation_created_id",
        "feed_messages",
        ["conversation_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_feed_conversation_participants_user_conversation",
        "feed_conversation_participants",
        ["user_id", "conversation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_feed_conversation_participants_user_conversation",
        table_name="feed_conversation_participants",
    )
    op.drop_index(
        "ix_feed_messages_conversation_created_id",
        table_name="feed_messages",
    )
