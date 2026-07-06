import logging

from fastapi import APIRouter, Depends, Query, HTTPException, status, Header, BackgroundTasks, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc, delete, update, and_, or_
from sqlalchemy.orm import selectinload
from core.db import get_db, AsyncSessionLocal
from core.deps import get_current_user, get_optional_current_user, require_estate_membership
from core.models import User, Post, PostLike, PostRepost, Poll, PollOption, PollVote, FavoriteUser, Unit, Block, UserUnit
from schemas import (
    FeedPostCreate, FeedReplyCreate, FeedPostResponse, FeedListResponse,
    PollVoteRequest, PollVoteResponse, ResidentResponse
)
from core.profanity import mask_profanity
from core.notifications import notifications
from core.media_urls import normalize_media_urls
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

router = APIRouter(prefix="/feed", tags=["Feed"])
logger = logging.getLogger(__name__)


def _format_unit_label(block: Block, unit: Unit) -> str:
    return f"{block.name}, {unit.unit_number}"


def _encode_post_cursor(post: Post) -> str:
    created_at = post.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return f"{created_at.isoformat()}|{post.id}"


def _parse_post_cursor(cursor: str) -> tuple[datetime | None, str]:
    if "|" not in cursor:
        return None, cursor

    created_at_raw, post_id = cursor.split("|", 1)
    try:
        created_at = datetime.fromisoformat(created_at_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc
    return created_at, post_id


async def _resolve_post_cursor(
    db: AsyncSession,
    *,
    cursor: str,
    estate_id: str | None = None,
    author_id: str | None = None,
) -> tuple[datetime, str]:
    cursor_created_at, cursor_post_id = _parse_post_cursor(cursor)
    if cursor_created_at is not None:
        return cursor_created_at, cursor_post_id

    stmt = select(Post.created_at, Post.id).where(
        Post.id == cursor_post_id,
        Post.is_deleted == False,
    )
    if estate_id:
        stmt = stmt.where(Post.estate_id == estate_id)
    if author_id:
        stmt = stmt.where(Post.author_id == author_id)

    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=400, detail="Invalid cursor")
    return row


async def _get_estate_post(
    db: AsyncSession,
    *,
    post_id: str,
    estate_id: str | None = None,
    options: tuple[Any, ...] = (),
) -> Post | None:
    stmt = select(Post)
    for option in options:
        stmt = stmt.options(option)
    stmt = stmt.where(
        Post.id == post_id,
        Post.is_deleted == False,
    )
    if estate_id:
        stmt = stmt.where(Post.estate_id == estate_id)
    return (await db.execute(stmt)).scalars().first()


async def _load_user_unit_labels(db: AsyncSession, user_ids: List[str]) -> Dict[str, str]:
    if not user_ids:
        return {}

    stmt = (
        select(UserUnit.user_id, Unit.unit_number, Block.name, UserUnit.is_primary)
        .join(Unit, UserUnit.unit_id == Unit.id)
        .join(Block, Unit.block_id == Block.id)
        .where(UserUnit.user_id.in_(user_ids))
        .order_by(UserUnit.user_id, desc(UserUnit.is_primary), Unit.unit_number)
    )
    rows = (await db.execute(stmt)).all()

    labels: Dict[str, str] = {}
    for user_id, unit_number, block_name, _ in rows:
        labels.setdefault(user_id, f"{block_name}, {unit_number}")
    return labels


async def _load_post_unit_labels(db: AsyncSession, posts: List[Post]) -> Dict[str, str]:
    labels: Dict[str, str] = {}
    unresolved_unit_ids: set[str] = set()
    fallback_user_ids: set[str] = set()
    posts_by_unit_id: Dict[str, List[str]] = {}

    for post in posts:
        if post.unit and post.unit.block:
            labels[post.id] = _format_unit_label(post.unit.block, post.unit)
        elif post.unit_id:
            unresolved_unit_ids.add(post.unit_id)
            posts_by_unit_id.setdefault(post.unit_id, []).append(post.id)
        else:
            fallback_user_ids.add(post.author_id)

    if unresolved_unit_ids:
        unit_stmt = (
            select(Unit.id, Unit.unit_number, Block.name)
            .join(Block, Unit.block_id == Block.id)
            .where(Unit.id.in_(unresolved_unit_ids))
        )
        for unit_id, unit_number, block_name in (await db.execute(unit_stmt)).all():
            label = f"{block_name}, {unit_number}"
            for post_id in posts_by_unit_id.get(unit_id, []):
                labels.setdefault(post_id, label)

    missing_post_user_ids = {post.author_id for post in posts if post.id not in labels}
    fallback_labels = await _load_user_unit_labels(db, list(fallback_user_ids | missing_post_user_ids))
    for post in posts:
        if post.id not in labels and post.author_id in fallback_labels:
            labels[post.id] = fallback_labels[post.author_id]

    return labels


async def _load_reply_counts(db: AsyncSession, post_ids: List[str]) -> Dict[str, int]:
    if not post_ids:
        return {}

    stmt = (
        select(Post.reply_to_id, func.count(Post.id))
        .where(Post.reply_to_id.in_(post_ids), Post.is_deleted == False)
        .group_by(Post.reply_to_id)
    )
    return {reply_to_id: count for reply_to_id, count in (await db.execute(stmt)).all()}


async def _load_like_data(
    db: AsyncSession,
    *,
    post_ids: List[str],
    current_user_id: str | None,
) -> tuple[Dict[str, int], set[str]]:
    if not post_ids:
        return {}, set()

    count_stmt = (
        select(PostLike.post_id, func.count(PostLike.id))
        .where(PostLike.post_id.in_(post_ids))
        .group_by(PostLike.post_id)
    )
    liked_stmt = select(PostLike.post_id).where(
        PostLike.post_id.in_(post_ids),
    )
    if current_user_id:
        liked_stmt = liked_stmt.where(PostLike.user_id == current_user_id)
    else:
        like_counts = {post_id: count for post_id, count in (await db.execute(count_stmt)).all()}
        return like_counts, set()

    like_counts = {post_id: count for post_id, count in (await db.execute(count_stmt)).all()}
    liked_post_ids = set((await db.execute(liked_stmt)).scalars().all())
    return like_counts, liked_post_ids


async def _load_poll_data_map(
    db: AsyncSession,
    *,
    poll_ids: List[str],
    current_user_id: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    if not poll_ids:
        return {}

    poll_stmt = select(Poll.id, Poll.end_at).where(Poll.id.in_(poll_ids))
    poll_rows = (await db.execute(poll_stmt)).all()
    poll_data = {
        poll_id: {"options": [], "votes": [], "user_vote": None, "end_at": end_at}
        for poll_id, end_at in poll_rows
    }

    options_stmt = select(PollOption.poll_id, PollOption.index, PollOption.text).where(
        PollOption.poll_id.in_(poll_ids)
    ).order_by(PollOption.poll_id, PollOption.index)
    option_rows = (await db.execute(options_stmt)).all()
    options_by_poll: Dict[str, List[tuple[int, str]]] = {}
    for poll_id, option_index, option_text in option_rows:
        options_by_poll.setdefault(poll_id, []).append((option_index, option_text))

    vote_counts_stmt = (
        select(PollVote.poll_id, PollVote.option_index, func.count(PollVote.id))
        .where(PollVote.poll_id.in_(poll_ids))
        .group_by(PollVote.poll_id, PollVote.option_index)
    )
    vote_counts = {
        (poll_id, option_index): count
        for poll_id, option_index, count in (await db.execute(vote_counts_stmt)).all()
    }

    user_votes: Dict[str, int] = {}
    if current_user_id:
        user_vote_stmt = select(PollVote.poll_id, PollVote.option_index).where(
            PollVote.poll_id.in_(poll_ids),
            PollVote.user_id == current_user_id,
        )
        user_votes = {
            poll_id: option_index
            for poll_id, option_index in (await db.execute(user_vote_stmt)).all()
        }

    for poll_id, poll_payload in poll_data.items():
        poll_options = options_by_poll.get(poll_id, [])
        poll_payload["options"] = [option_text for _, option_text in poll_options]
        poll_payload["votes"] = [
            vote_counts.get((poll_id, option_index), 0)
            for option_index, _ in poll_options
        ]
        poll_payload["user_vote"] = user_votes.get(poll_id)

    return poll_data


async def _build_poll_data(
    db: AsyncSession,
    post: Post,
    *,
    current_user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    poll_payloads = await _load_poll_data_map(
        db,
        poll_ids=[post.poll_id] if post.poll_id else [],
        current_user_id=current_user_id,
    )
    return poll_payloads.get(post.poll_id)


async def _serialize_posts(
    db: AsyncSession,
    posts: List[Post],
    *,
    current_user_id: str | None,
    reply_counts: Optional[Dict[str, int]] = None,
    reply_to_authors: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    if not posts:
        return []

    post_ids = [post.id for post in posts]
    like_counts, liked_post_ids = await _load_like_data(
        db,
        post_ids=post_ids,
        current_user_id=current_user_id,
    )
    reply_counts = reply_counts or {}
    author_units = await _load_post_unit_labels(db, posts)
    poll_payloads = await _load_poll_data_map(
        db,
        poll_ids=[post.poll_id for post in posts if post.poll_id],
        current_user_id=current_user_id,
    )

    serialized = []
    for post in posts:
        media_urls = normalize_media_urls(post.media_urls)
        serialized.append(
            {
                "id": post.id,
                "author_id": post.author_id,
                "author_name": post.author.full_name if post.author else "Unknown",
                "author_avatar": post.author.profile_image_url if post.author else None,
                "author_unit": author_units.get(post.id) or "Resident",
                "content": post.content,
                "media_urls": media_urls,
                "media": [{"uri": u, "type": "image"} for u in media_urls],
                "created_at": post.created_at,
                "like_count": like_counts.get(post.id, 0),
                "reply_count": reply_counts.get(post.id, 0),
                "repost_count": 0,
                "is_liked": post.id in liked_post_ids,
                "is_reposted": False,
                "reply_to_id": post.reply_to_id,
                "reply_to_author": (reply_to_authors or {}).get(post.id),
                "poll": poll_payloads.get(post.poll_id),
            }
        )

    return serialized


async def require_feed_context(
    x_estate_id: Optional[str] = Header(None, alias="X-Estate-ID"),
    x_unit_id: Optional[str] = Header(None, alias="X-Unit-ID"),
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if x_estate_id and x_estate_id != current_user.estate_id:
        raise HTTPException(status_code=403, detail="X-Estate-ID does not match the authenticated user's estate")

    unit = None
    block = None

    if x_unit_id:
        stmt = (
            select(Unit, Block)
            .join(Block, Unit.block_id == Block.id)
            .join(UserUnit, UserUnit.unit_id == Unit.id)
            .where(
                UserUnit.user_id == current_user.id,
                UserUnit.unit_id == x_unit_id,
                Block.estate_id == current_user.estate_id,
            )
        )
        row = (await db.execute(stmt)).first()
        if not row:
            raise HTTPException(status_code=403, detail="Access to this unit denied")
        unit, block = row
    else:
        stmt = (
            select(Unit, Block)
            .join(Block, Unit.block_id == Block.id)
            .join(UserUnit, UserUnit.unit_id == Unit.id)
            .where(
                UserUnit.user_id == current_user.id,
                UserUnit.is_primary == True,
                Block.estate_id == current_user.estate_id,
            )
        )
        row = (await db.execute(stmt)).first()
        if row:
            unit, block = row

    if not unit or not block:
        fallback_stmt = (
            select(UserUnit, Unit, Block)
            .join(Unit, UserUnit.unit_id == Unit.id)
            .join(Block, Unit.block_id == Block.id)
            .where(
                UserUnit.user_id == current_user.id,
                Block.estate_id == current_user.estate_id,
            )
        )
        row = (await db.execute(fallback_stmt)).first()
        if row:
            _, unit, block = row

    return {
        "current_user": current_user,
        "unit": unit,
        "unit_label": _format_unit_label(block, unit) if unit and block else "Resident",
    }


async def _send_post_reply_notification(user_id: str, replier_name: str, post_id: str):
    async with AsyncSessionLocal() as db:
        try:
            await notifications.send_post_reply(
                db=db,
                user_id=user_id,
                replier_name=replier_name,
                post_id=post_id,
            )
        except Exception as exc:
            logger.error(
                "Reply notification dispatch failed: %s",
                exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )

@router.get("/posts", response_model=FeedListResponse, response_model_by_alias=False)
async def get_feed(
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, le=50),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the public community feed.
    """
    # Base query: all posts, not deleted, newest first
    stmt = select(Post).options(
        selectinload(Post.author),
        selectinload(Post.poll),
        selectinload(Post.unit).selectinload(Unit.block),
    ).where(
        Post.is_deleted == False,
        Post.reply_to_id == None
    ).order_by(desc(Post.created_at), desc(Post.id))

    if cursor:
        cursor_created_at, cursor_post_id = await _resolve_post_cursor(
            db,
            cursor=cursor,
        )
        stmt = stmt.where(
            or_(
                Post.created_at < cursor_created_at,
                and_(Post.created_at == cursor_created_at, Post.id < cursor_post_id),
            )
        )
        
    stmt = stmt.limit(limit)
    
    result = await db.execute(stmt)
    posts = result.scalars().all()
    
    next_cursor = _encode_post_cursor(posts[-1]) if len(posts) == limit else None
    
    reply_counts = await _load_reply_counts(db, [post.id for post in posts])
    enriched_posts = await _serialize_posts(
        db,
        posts,
        current_user_id=current_user.id if current_user else None,
        reply_counts=reply_counts,
    )

    return {"posts": enriched_posts, "next_cursor": next_cursor}


@router.get("/posts/{post_id}", response_model=FeedPostResponse, response_model_by_alias=False)
async def get_feed_post(
    post_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a single public feed post.
    """
    stmt = (
        select(Post)
        .options(
            selectinload(Post.author),
            selectinload(Post.poll),
            selectinload(Post.unit).selectinload(Unit.block),
        )
        .where(
            Post.id == post_id,
            Post.is_deleted == False,
        )
    )
    post = (await db.execute(stmt)).scalars().first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    serialized_posts = await _serialize_posts(
        db,
        [post],
        current_user_id=current_user.id if current_user else None,
        reply_counts=await _load_reply_counts(db, [post.id]),
    )
    return serialized_posts[0]

@router.post("/posts", response_model=FeedPostResponse, status_code=status.HTTP_201_CREATED, response_model_by_alias=False)
async def create_post(
    post_data: FeedPostCreate,
    context: Dict[str, Any] = Depends(require_feed_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new post in the estate feed.
    """
    current_user = context["current_user"]

    if not post_data.content and not post_data.media_urls and not post_data.poll:
        raise HTTPException(status_code=400, detail="Post must have content, media or a poll.")
        
    # Profanity filtering
    masked_content = mask_profanity(post_data.content) if post_data.content else None
    
    poll_id = None
    if post_data.poll:
        options = post_data.poll.get("options", [])
        if len(options) < 2 or len(options) > 4:
            raise HTTPException(status_code=400, detail="Poll must have 2-4 options.")
            
        end_at_str = post_data.poll.get("endAt") or post_data.poll.get("end_at")
        end_at_dt = None
        if end_at_str:
            try:
                # Handle ISO formatting, e.g. "2026-12-31T23:59:59Z" -> "+00:00"
                if end_at_str.endswith('Z'):
                    end_at_str = end_at_str[:-1] + '+00:00'
                end_at_dt = datetime.fromisoformat(end_at_str)
            except ValueError:
                end_at_dt = None

        new_poll = Poll(end_at=end_at_dt)
        db.add(new_poll)
        await db.flush()
        
        for i, opt_text in enumerate(options):
            db.add(PollOption(poll_id=new_poll.id, text=opt_text, index=i))
            
        poll_id = new_poll.id

    media_urls = normalize_media_urls(post_data.media_urls)

    new_post = Post(
        author_id=current_user.id,
        estate_id=current_user.estate_id,
        unit_id=context["unit"].id,
        content=masked_content,
        media_urls=media_urls,
        media=[{"uri": u, "type": "image"} for u in media_urls],
        poll_id=poll_id
    )
    
    db.add(new_post)
    await db.commit()
    await db.refresh(new_post)
    
    # Return basic response (frontend can re-fetch for enriched data)
    return {
        "id": new_post.id,
        "author_id": new_post.author_id,
        "author_name": current_user.full_name,
        "author_avatar": current_user.profile_image_url,
        "author_unit": context["unit_label"],
        "content": new_post.content,
        "media_urls": normalize_media_urls(new_post.media_urls),
        "media": [{"uri": u, "type": "image"} for u in normalize_media_urls(new_post.media_urls)],
        "created_at": new_post.created_at,
        "like_count": 0,
        "reply_count": 0,
        "repost_count": 0,
        "is_liked": False,
        "is_reposted": False,
        "poll": await _build_poll_data(db, new_post),
    }

@router.post("/posts/{post_id}/like")
async def like_post(
    post_id: str,
    context: Dict[str, Any] = Depends(require_feed_context),
    db: AsyncSession = Depends(get_db),
):
    current_user = context["current_user"]
    post = await _get_estate_post(db, post_id=post_id, estate_id=current_user.estate_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    stmt = select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == current_user.id)
    result = await db.execute(stmt)
    existing = result.scalars().first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Post already liked")
        
    db.add(PostLike(post_id=post_id, user_id=current_user.id))
    await db.commit()
    
    count_stmt = select(func.count(PostLike.id)).where(PostLike.post_id == post_id)
    count = (await db.execute(count_stmt)).scalar() or 0
    return {"like_count": count}

@router.delete("/posts/{post_id}/like")
async def unlike_post(
    post_id: str,
    context: Dict[str, Any] = Depends(require_feed_context),
    db: AsyncSession = Depends(get_db),
):
    current_user = context["current_user"]
    post = await _get_estate_post(db, post_id=post_id, estate_id=current_user.estate_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    stmt = select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == current_user.id)
    result = await db.execute(stmt)
    existing = result.scalars().first()
    
    if not existing:
        raise HTTPException(status_code=404, detail="Like not found")
        
    await db.delete(existing)
    await db.commit()
    
    count_stmt = select(func.count(PostLike.id)).where(PostLike.post_id == post_id)
    count = (await db.execute(count_stmt)).scalar() or 0
    return {"like_count": count}

@router.post("/posts/{post_id}/poll/vote", response_model=PollVoteResponse, response_model_by_alias=False)
async def vote_poll(
    post_id: str,
    vote: PollVoteRequest,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    post = await _get_estate_post(db, post_id=post_id, estate_id=current_user.estate_id)
    
    if not post or not post.poll_id:
        raise HTTPException(status_code=404, detail="Poll not found")
        
    # Check if user already voted
    existing_vote_stmt = select(PollVote).where(PollVote.poll_id == post.poll_id, PollVote.user_id == current_user.id)
    if (await db.execute(existing_vote_stmt)).scalars().first():
        raise HTTPException(status_code=400, detail="User already voted")
        
    # Verify option index
    option_stmt = select(PollOption).where(PollOption.poll_id == post.poll_id, PollOption.index == vote.option_index)
    if not (await db.execute(option_stmt)).scalars().first():
        raise HTTPException(status_code=400, detail="Invalid option index")
        
    db.add(PollVote(poll_id=post.poll_id, user_id=current_user.id, option_index=vote.option_index))
    await db.commit()
    
    await db.refresh(post)
    return {
        "success": True,
        "poll": await _build_poll_data(db, post, current_user_id=current_user.id),
    }

@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: str,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    post = await _get_estate_post(db, post_id=post_id, estate_id=current_user.estate_id)
    
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
        
    if post.author_id != current_user.id:
        # Check if admin (optional, for now strictly owner)
        raise HTTPException(status_code=403, detail="Permission denied")
        
    target_rows = [(post.id, post.poll_id)]
    if post.reply_to_id is None:
        reply_rows = (
            await db.execute(
                select(Post.id, Post.poll_id).where(Post.reply_to_id == post.id, Post.is_deleted == False)
            )
        ).all()
        target_rows.extend(reply_rows)

    target_post_ids = [target_post_id for target_post_id, _ in target_rows]
    target_poll_ids = [poll_id for _, poll_id in target_rows if poll_id]

    await db.execute(delete(PostLike).where(PostLike.post_id.in_(target_post_ids)))
    await db.execute(delete(PostRepost).where(PostRepost.post_id.in_(target_post_ids)))

    if target_poll_ids:
        await db.execute(delete(PollVote).where(PollVote.poll_id.in_(target_poll_ids)))
        await db.execute(delete(PollOption).where(PollOption.poll_id.in_(target_poll_ids)))
        await db.execute(delete(Poll).where(Poll.id.in_(target_poll_ids)))

    await db.execute(
        update(Post)
        .where(Post.id.in_(target_post_ids))
        .values(is_deleted=True, media=[], media_urls=[])
    )
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/users/{user_id}/posts", response_model=FeedListResponse, response_model_by_alias=False)
async def get_user_posts(
    user_id: str,
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, le=50),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get posts from a specific user across the public feed.
    """
    stmt = select(Post).options(
        selectinload(Post.author),
        selectinload(Post.poll),
        selectinload(Post.unit).selectinload(Unit.block),
    ).where(
        Post.author_id == user_id,
        Post.is_deleted == False,
        Post.reply_to_id == None,
    ).order_by(desc(Post.created_at), desc(Post.id))

    if cursor:
        cursor_created_at, cursor_post_id = await _resolve_post_cursor(
            db,
            cursor=cursor,
            author_id=user_id,
        )
        stmt = stmt.where(
            or_(
                Post.created_at < cursor_created_at,
                and_(Post.created_at == cursor_created_at, Post.id < cursor_post_id),
            )
        )
        
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    posts = result.scalars().all()
    
    enriched = await _serialize_posts(
        db,
        posts,
        current_user_id=current_user.id if current_user else None,
        reply_counts=await _load_reply_counts(db, [post.id for post in posts]),
    )

    return {"posts": enriched, "next_cursor": _encode_post_cursor(posts[-1]) if len(posts) == limit else None}

@router.get("/favorites", response_model=List[ResidentResponse])
async def get_favorites(
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).join(FavoriteUser, FavoriteUser.favorite_user_id == User.id).where(
        FavoriteUser.user_id == current_user.id
    )
    result = await db.execute(stmt)
    favorites = result.scalars().all()
    
    return [
        {
            "id": f.id,
            "name": f.full_name,
            "avatar": f.profile_image_url,
            "unit": "Neighbor"
        } for f in favorites
    ]

@router.post("/favorites")
async def add_favorite(
    req: dict, # {"userId": "..."}
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    fav_id = req.get("userId")
    if not fav_id:
        raise HTTPException(status_code=400, detail="userId required")
        
    # Check if already exists
    stmt = select(FavoriteUser).where(FavoriteUser.user_id == current_user.id, FavoriteUser.favorite_user_id == fav_id)
    if (await db.execute(stmt)).scalars().first():
        return {"success": True, "message": "Already in favorites"}
        
    db.add(FavoriteUser(user_id=current_user.id, favorite_user_id=fav_id))
    await db.commit()
    return {"success": True}

@router.delete("/favorites/{fav_user_id}")
async def remove_favorite(
    fav_user_id: str,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    stmt = delete(FavoriteUser).where(
        FavoriteUser.user_id == current_user.id, 
        FavoriteUser.favorite_user_id == fav_user_id
    )
    await db.execute(stmt)
    await db.commit()
    return status.HTTP_204_NO_CONTENT

@router.post("/posts/{post_id}/replies", response_model=FeedPostResponse, status_code=status.HTTP_201_CREATED, response_model_by_alias=False)
async def reply_to_post(
    background_tasks: BackgroundTasks,
    post_id: str,
    reply_data: FeedReplyCreate,
    context: Dict[str, Any] = Depends(require_feed_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Reply to a post.
    """
    current_user = context["current_user"]

    # 1. Check parent post
    parent = await _get_estate_post(
        db,
        post_id=post_id,
        estate_id=current_user.estate_id,
        options=(selectinload(Post.author),),
    )
    if not parent:
        raise HTTPException(status_code=404, detail="Parent post not found")
        
    if not reply_data.content and not reply_data.media_urls:
        raise HTTPException(status_code=400, detail="Reply must have content or media.")
        
    # Profanity filtering
    masked_content = mask_profanity(reply_data.content) if reply_data.content else None
    
    media_urls = normalize_media_urls(reply_data.media_urls)

    new_reply = Post(
        author_id=current_user.id,
        estate_id=current_user.estate_id,
        unit_id=context["unit"].id,
        content=masked_content,
        media_urls=media_urls,
        media=[{"uri": u, "type": "image"} for u in media_urls],
        reply_to_id=post_id
    )
    
    db.add(new_reply)
    await db.commit()
    await db.refresh(new_reply)
    
    # Send notification to parent author if it's not the same user
    if parent.author_id != current_user.id:
        background_tasks.add_task(
            _send_post_reply_notification,
            parent.author_id,
            current_user.full_name,
            parent.id,
        )
            
    return {
        "id": new_reply.id,
        "author_id": new_reply.author_id,
        "author_name": current_user.full_name,
        "author_avatar": current_user.profile_image_url,
        "author_unit": context["unit_label"],
        "content": new_reply.content,
        "media_urls": normalize_media_urls(new_reply.media_urls),
        "media": [{"uri": u, "type": "image"} for u in normalize_media_urls(new_reply.media_urls)],
        "created_at": new_reply.created_at,
        "like_count": 0,
        "reply_count": 0,
        "repost_count": 0,
        "is_liked": False,
        "is_reposted": False,
        "reply_to_id": post_id,
        "reply_to_author": reply_data.reply_to_author or (parent.author.full_name if parent.author else "Unknown"),
    }

@router.get("/posts/{post_id}/replies", response_model=List[FeedPostResponse], response_model_by_alias=False)
async def get_post_replies(
    post_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get replies for a specific post from the public feed.
    Returns a flat array instead of a paginated object.
    """
    # 1. Check parent post
    parent = await _get_estate_post(
        db,
        post_id=post_id,
        estate_id=None,
        options=(selectinload(Post.author),),
    )
    if not parent:
        raise HTTPException(status_code=404, detail="Parent post not found")

    stmt = select(Post).options(
        selectinload(Post.author),
        selectinload(Post.poll),
        selectinload(Post.unit).selectinload(Unit.block),
    ).where(
        Post.reply_to_id == post_id,
        Post.is_deleted == False
    ).order_by(Post.created_at)
    
    result = await db.execute(stmt)
    replies = result.scalars().all()
    
    return await _serialize_posts(
        db,
        replies,
        current_user_id=current_user.id if current_user else None,
        reply_to_authors={
            reply.id: (parent.author.full_name if parent.author else "Unknown")
            for reply in replies
        },
    )
