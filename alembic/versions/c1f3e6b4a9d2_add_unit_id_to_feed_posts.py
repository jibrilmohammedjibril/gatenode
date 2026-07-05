"""add unit_id to feed posts

Revision ID: c1f3e6b4a9d2
Revises: 066a01d251c0
Create Date: 2026-03-17 16:24:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1f3e6b4a9d2"
down_revision: Union[str, None] = "066a01d251c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("feed_posts")}
    foreign_keys = {fk["constrained_columns"][0] for fk in inspector.get_foreign_keys("feed_posts") if fk.get("constrained_columns")}
    indexes = {index["name"] for index in inspector.get_indexes("feed_posts")}

    if "unit_id" not in columns:
        op.add_column("feed_posts", sa.Column("unit_id", sa.String(), nullable=True))

    if "unit_id" not in foreign_keys:
        op.create_foreign_key(
            "fk_feed_posts_unit_id_units",
            "feed_posts",
            "units",
            ["unit_id"],
            ["id"],
        )

    if "ix_feed_posts_unit_id" not in indexes:
        op.create_index("ix_feed_posts_unit_id", "feed_posts", ["unit_id"], unique=False)

    op.execute(
        sa.text(
            """
            WITH ranked_units AS (
                SELECT
                    uu.user_id,
                    uu.unit_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY uu.user_id
                        ORDER BY uu.is_primary DESC, uu.id ASC
                    ) AS rn
                FROM user_units AS uu
            )
            UPDATE feed_posts AS fp
            SET unit_id = ru.unit_id
            FROM ranked_units AS ru
            JOIN units AS u ON u.id = ru.unit_id
            JOIN blocks AS b ON b.id = u.block_id
            WHERE fp.unit_id IS NULL
              AND fp.author_id = ru.user_id
              AND ru.rn = 1
              AND fp.estate_id = b.estate_id
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("feed_posts")}
    indexes = {index["name"] for index in inspector.get_indexes("feed_posts")}
    foreign_key_names = {fk["name"] for fk in inspector.get_foreign_keys("feed_posts")}

    if "ix_feed_posts_unit_id" in indexes:
        op.drop_index("ix_feed_posts_unit_id", table_name="feed_posts")

    if "fk_feed_posts_unit_id_units" in foreign_key_names:
        op.drop_constraint("fk_feed_posts_unit_id_units", "feed_posts", type_="foreignkey")

    if "unit_id" in columns:
        op.drop_column("feed_posts", "unit_id")
