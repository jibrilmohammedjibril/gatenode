import argparse
import asyncio
import sys

from sqlalchemy import select

from core.db import AsyncSessionLocal
from core.media_urls import normalize_media_urls
from core.models import Message, Post


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize stored feed and chat media URLs in the database.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the changes. Without this flag the script runs in dry-run mode.",
    )
    return parser.parse_args()


async def _backfill_posts(*, apply_changes: bool) -> tuple[int, int]:
    scanned = 0
    changed = 0

    async with AsyncSessionLocal() as db:
        posts = (await db.execute(select(Post))).scalars().all()

        for post in posts:
            scanned += 1
            original_urls = list(post.media_urls or [])
            normalized_urls = normalize_media_urls(original_urls)
            if normalized_urls != original_urls:
                changed += 1
                print(f"post {post.id}")
                print(f"  before={original_urls}")
                print(f"  after ={normalized_urls}")
                if apply_changes:
                    post.media_urls = normalized_urls
                    post.media = [{"uri": url, "type": "image"} for url in normalized_urls]
                    db.add(post)

        if apply_changes:
            await db.commit()

    return scanned, changed


async def _backfill_messages(*, apply_changes: bool) -> tuple[int, int]:
    scanned = 0
    changed = 0

    async with AsyncSessionLocal() as db:
        messages = (await db.execute(select(Message))).scalars().all()

        for message in messages:
            scanned += 1
            original_urls = list(message.media_urls or [])
            normalized_urls = normalize_media_urls(original_urls)
            if normalized_urls != original_urls:
                changed += 1
                print(f"message {message.id}")
                print(f"  before={original_urls}")
                print(f"  after ={normalized_urls}")
                if apply_changes:
                    message.media_urls = normalized_urls
                    db.add(message)

        if apply_changes:
            await db.commit()

    return scanned, changed


async def main() -> int:
    args = parse_args()

    post_scanned, post_changed = await _backfill_posts(apply_changes=args.apply)
    msg_scanned, msg_changed = await _backfill_messages(apply_changes=args.apply)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"mode={mode}")
    print(f"posts_scanned={post_scanned} posts_changed={post_changed}")
    print(f"messages_scanned={msg_scanned} messages_changed={msg_changed}")

    if not args.apply:
        print("No changes were written. Re-run with --apply to persist updates.")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
