import asyncio
import logging
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Query, HTTPException, status, BackgroundTasks, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc, and_, or_, update
from core.db import AsyncSessionLocal, get_db
from core.deps import get_current_user, require_estate_membership
from core.models import User, Unit, Block, Estate, UserUnit, Conversation, ConversationParticipant, Message
from schemas import (
    ConversationResponse, MessageResponse, MessageListResponse, 
    ConversationCreateRequest, MessageCreateRequest, ResidentResponse,
    ParticipantAddRequest, ResidentHouseGroupResponse
)
from core.events import event_manager
from core.media_urls import normalize_media_urls
from core.notifications import notifications
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

router = APIRouter(prefix="/feed", tags=["Messaging"])
logger = logging.getLogger(__name__)


def _encode_message_cursor(message: Message | SimpleNamespace) -> str:
    created_at = message.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return f"{created_at.isoformat()}|{message.id}"


def _parse_message_cursor(cursor: str) -> tuple[Optional[datetime], str]:
    raw_cursor = (cursor or "").strip()
    if not raw_cursor:
        raise ValueError("Cursor is required")

    if "|" not in raw_cursor:
        return None, raw_cursor

    raw_created_at, message_id = raw_cursor.split("|", 1)
    created_at = datetime.fromisoformat(raw_created_at)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at, message_id


def _serialize_message(message: Message, *, from_name: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": message.id,
        "fromId": message.from_id,
        "fromName": from_name or (message.sender.full_name if getattr(message, "sender", None) else "Unknown"),
        "text": message.text,
        "createdAt": message.created_at,
        "mediaUrls": normalize_media_urls(message.media_urls),
        "readAt": message.read_at,
    }


def _build_house_search_text():
    return func.lower(
        func.concat(
            func.coalesce(Unit.unit_number, ""),
            " ",
            func.coalesce(Block.name, ""),
            " ",
            func.coalesce(Estate.address, ""),
            " ",
            func.coalesce(Estate.name, ""),
        )
    )


def _build_house_label(unit_number: Optional[str], block_name: Optional[str]) -> str:
    if unit_number and block_name:
        return f"{unit_number}, {block_name}"
    return unit_number or block_name or "Unassigned"


async def _load_conversation_participants(
    db: AsyncSession,
    conversation_ids: list[str],
) -> dict[str, list[dict[str, Optional[str]]]]:
    if not conversation_ids:
        return {}

    stmt = (
        select(ConversationParticipant.conversation_id, User)
        .join(User, ConversationParticipant.user_id == User.id)
        .where(ConversationParticipant.conversation_id.in_(conversation_ids))
    )
    rows = (await db.execute(stmt)).all()

    participants_map: dict[str, list[dict[str, Optional[str]]]] = {conversation_id: [] for conversation_id in conversation_ids}
    for conversation_id, participant in rows:
        participants_map.setdefault(conversation_id, []).append(
            {"id": participant.id, "name": participant.full_name, "avatar": participant.profile_image_url}
        )
    return participants_map


async def _load_last_messages(
    db: AsyncSession,
    conversation_ids: list[str],
) -> dict[str, dict[str, Any]]:
    if not conversation_ids:
        return {}

    ranked_messages = (
        select(
            Message.conversation_id.label("conversation_id"),
            Message.text.label("text"),
            Message.created_at.label("created_at"),
            Message.from_id.label("from_id"),
            func.row_number().over(
                partition_by=Message.conversation_id,
                order_by=(Message.created_at.desc(), Message.id.desc()),
            ).label("row_num"),
        )
        .where(Message.conversation_id.in_(conversation_ids))
        .subquery()
    )

    stmt = select(
        ranked_messages.c.conversation_id,
        ranked_messages.c.text,
        ranked_messages.c.created_at,
        ranked_messages.c.from_id,
    ).where(ranked_messages.c.row_num == 1)
    rows = (await db.execute(stmt)).all()

    return {
        conversation_id: {
            "text": text,
            "createdAt": created_at,
            "fromId": from_id,
        }
        for conversation_id, text, created_at, from_id in rows
    }


async def _load_unread_counts(
    db: AsyncSession,
    *,
    current_user_id: str,
    last_read_map: dict[str, Optional[datetime]],
) -> dict[str, int]:
    if not last_read_map:
        return {}

    unread_conditions = []
    for conversation_id, last_read_at in last_read_map.items():
        conditions = [
            Message.conversation_id == conversation_id,
            Message.from_id != current_user_id,
        ]
        if last_read_at is not None:
            conditions.append(Message.created_at > last_read_at)
        unread_conditions.append(and_(*conditions))

    stmt = (
        select(Message.conversation_id, func.count(Message.id))
        .where(or_(*unread_conditions))
        .group_by(Message.conversation_id)
    )
    rows = (await db.execute(stmt)).all()
    return {conversation_id: count for conversation_id, count in rows}


async def _load_conversation_participant_ids(db: AsyncSession, conversation_id: str) -> list[str]:
    stmt = select(ConversationParticipant.user_id).where(
        ConversationParticipant.conversation_id == conversation_id
    )
    return (await db.execute(stmt)).scalars().all()


async def _publish_to_users(
    user_ids: list[str],
    event_type: str,
    payload: Dict[str, Any],
):
    if not user_ids:
        return

    results = await asyncio.gather(
        *(event_manager.publish(event_type, payload, participant_id) for participant_id in user_ids),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, Exception):
            logger.error(
                "Conversation event fanout failed: %s",
                result,
                exc_info=(type(result), result, result.__traceback__),
            )


def _build_message_preview(text: Optional[str], media_urls: list[str]) -> str:
    normalized_text = " ".join((text or "").split())
    if normalized_text:
        if len(normalized_text) > 120:
            return f"{normalized_text[:117].rstrip()}..."
        return normalized_text
    if media_urls:
        return "Sent media"
    return "New message"


async def _send_chat_message_notifications(
    recipient_ids: list[str],
    *,
    sender_name: str,
    conversation_id: str,
    message_preview: str,
    group_name: Optional[str] = None,
):
    if not recipient_ids:
        return

    async with AsyncSessionLocal() as db:
        for recipient_id in recipient_ids:
            try:
                await notifications.send_chat_message(
                    db=db,
                    user_id=recipient_id,
                    sender_name=sender_name,
                    conversation_id=conversation_id,
                    message_preview=message_preview,
                    group_name=group_name,
                )
            except Exception as exc:
                logger.error(
                    "Chat notification dispatch failed for user %s: %s",
                    recipient_id,
                    exc,
                    exc_info=(type(exc), exc, exc.__traceback__),
                )


async def _remove_conversation_membership(
    db: AsyncSession,
    *,
    conversation: Conversation,
    user_id: str,
) -> list[str]:
    participant_stmt = select(ConversationParticipant).where(
        ConversationParticipant.conversation_id == conversation.id,
        ConversationParticipant.user_id == user_id,
    )
    participant = (await db.execute(participant_stmt)).scalars().first()
    if not participant:
        raise HTTPException(status_code=404, detail="Conversation not found for this user")

    await db.delete(participant)
    await db.flush()

    remaining_participant_ids = await _load_conversation_participant_ids(db, conversation.id)
    if remaining_participant_ids:
        await db.execute(
            update(Conversation)
            .where(Conversation.id == conversation.id)
            .values(updated_at=datetime.utcnow())
        )
    else:
        await db.delete(conversation)

    await db.commit()
    return remaining_participant_ids

@router.get("/conversations", response_model=List[ConversationResponse])
async def get_conversations(
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's conversations.
    """
    stmt = (
        select(Conversation, ConversationParticipant.last_read_at)
        .join(
            ConversationParticipant,
            and_(
                ConversationParticipant.conversation_id == Conversation.id,
                ConversationParticipant.user_id == current_user.id,
            ),
        )
        .order_by(desc(Conversation.updated_at))
    )

    rows = (await db.execute(stmt)).all()
    conversations = [conversation for conversation, _ in rows]
    conversation_ids = [conversation.id for conversation in conversations]
    last_read_map = {conversation.id: last_read_at for conversation, last_read_at in rows}

    participants_map = await _load_conversation_participants(db, conversation_ids)
    last_messages_map = await _load_last_messages(db, conversation_ids)
    unread_counts = await _load_unread_counts(
        db,
        current_user_id=current_user.id,
        last_read_map=last_read_map,
    )

    enriched = []
    for conv in conversations:
        enriched.append({
            "id": conv.id,
            "participants": participants_map.get(conv.id, []),
            "isGroup": conv.is_group,
            "lastMessage": last_messages_map.get(conv.id),
            "unreadCount": unread_counts.get(conv.id, 0),
            "groupName": conv.group_name
        })
        
    return enriched

@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    req: ConversationCreateRequest,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a 1:1 or Group conversation.
    """
    if not req.participant_id and not req.participant_ids:
        raise HTTPException(status_code=400, detail="Participant(s) required.")
        
    if req.participant_id:
        # 1:1 Idempotency check
        stmt = select(Conversation).where(
            Conversation.is_group == False,
            Conversation.estate_id == current_user.estate_id
        ).join(ConversationParticipant).where(
            ConversationParticipant.user_id.in_([current_user.id, req.participant_id])
        ).group_by(Conversation.id).having(func.count(ConversationParticipant.id) == 2)
        
        # Above query is complex for asyncpg/SQLAlchemy sometimes. 
        # Simpler check:
        # Find all conversations current_user is in
        subq = select(ConversationParticipant.conversation_id).where(ConversationParticipant.user_id == current_user.id)
        # Find which of those have req.participant_id
        stmt = select(Conversation).where(
            Conversation.id.in_(subq),
            Conversation.is_group == False
        ).join(ConversationParticipant).where(ConversationParticipant.user_id == req.participant_id)
        
        existing = (await db.execute(stmt)).scalars().first()
        if existing:
            # Re-fetch for response
            return await get_single_conversation_enriched(existing.id, current_user.id, db)

        # Create new 1:1
        new_conv = Conversation(estate_id=current_user.estate_id, is_group=False)
        db.add(new_conv)
        await db.flush()
        db.add(ConversationParticipant(conversation_id=new_conv.id, user_id=current_user.id))
        db.add(ConversationParticipant(conversation_id=new_conv.id, user_id=req.participant_id))
        
    else:
        # Group
        new_conv = Conversation(estate_id=current_user.estate_id, is_group=True, group_name=req.group_name)
        db.add(new_conv)
        await db.flush()
        db.add(ConversationParticipant(conversation_id=new_conv.id, user_id=current_user.id))
        for pid in req.participant_ids:
            db.add(ConversationParticipant(conversation_id=new_conv.id, user_id=pid))
            
    await db.commit()
    return await get_single_conversation_enriched(new_conv.id, current_user.id, db)

@router.post("/conversations/{conversation_id}/participants", response_model=ConversationResponse)
async def add_participants(
    conversation_id: str,
    req: ParticipantAddRequest,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    """Add members to an existing group conversation."""
    # 1. Verify group conversation
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    conv = (await db.execute(stmt)).scalars().first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not conv.is_group:
        raise HTTPException(status_code=400, detail="Cannot add members to a 1:1 conversation")

    # 2. Verify current user is a participant
    p_stmt = select(ConversationParticipant).where(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id
    )
    if not (await db.execute(p_stmt)).scalars().first():
        raise HTTPException(status_code=403, detail="Not a participant")

    # 3. Handle duplicates
    existing_p_stmt = select(ConversationParticipant.user_id).where(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id.in_(req.participant_ids)
    )
    existing_ids = set((await db.execute(existing_p_stmt)).scalars().all())
    new_ids = set(req.participant_ids) - existing_ids
    
    if not new_ids:
        raise HTTPException(status_code=400, detail="Users already in group")

    # 4. Filter for valid users in the estate
    u_stmt = select(User.id).where(
        User.id.in_(new_ids),
        User.estate_id == current_user.estate_id,
        User.is_deleted.is_not(True)
    )
    valid_new_ids = (await db.execute(u_stmt)).scalars().all()
    if not valid_new_ids:
        raise HTTPException(status_code=400, detail="No valid participants to add")

    # 5. Insert new members
    for pid in valid_new_ids:
        db.add(ConversationParticipant(conversation_id=conversation_id, user_id=pid))

    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(updated_at=datetime.utcnow())
    )
    await db.commit()

    return await get_single_conversation_enriched(conversation_id, current_user.id, db)


@router.post("/conversations/{conversation_id}/leave")
async def leave_group_conversation(
    background_tasks: BackgroundTasks,
    conversation_id: str,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    """
    Leave an existing group conversation.
    """
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    conv = (await db.execute(stmt)).scalars().first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not conv.is_group:
        raise HTTPException(status_code=400, detail="Cannot leave a 1:1 conversation")
    remaining_participant_ids = await _remove_conversation_membership(
        db,
        conversation=conv,
        user_id=current_user.id,
    )

    if remaining_participant_ids:
        background_tasks.add_task(
            _publish_to_users,
            remaining_participant_ids,
            "feed:conversation_member_left",
            {
                "conversationId": conversation_id,
                "userId": current_user.id,
                "userName": current_user.full_name,
            },
        )

    return {
        "success": True,
        "conversationId": conversation_id,
        "left": True,
    }


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove a conversation from the authenticated user's chat list.
    """
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    conv = (await db.execute(stmt)).scalars().first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await _remove_conversation_membership(
        db,
        conversation=conv,
        user_id=current_user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def get_messages(
    conversation_id: str,
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    # Verify participation
    p_stmt = select(ConversationParticipant.id, ConversationParticipant.last_read_at).where(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id
    )
    participant_row = (await db.execute(p_stmt)).first()
    if participant_row is None:
        raise HTTPException(status_code=403, detail="Not a participant")

    stmt = (
        select(Message, User.full_name)
        .join(User, Message.from_id == User.id)
        .where(Message.conversation_id == conversation_id)
        .order_by(desc(Message.created_at), desc(Message.id))
    )

    if cursor:
        cursor_created_at, cursor_message_id = _parse_message_cursor(cursor)
        if cursor_created_at is None:
            legacy_cursor_stmt = select(Message.created_at).where(
                Message.id == cursor_message_id,
                Message.conversation_id == conversation_id,
            )
            cursor_created_at = (await db.execute(legacy_cursor_stmt)).scalars().first()
            if cursor_created_at is None:
                raise HTTPException(status_code=400, detail="Invalid cursor")

        stmt = stmt.where(
            or_(
                Message.created_at < cursor_created_at,
                and_(
                    Message.created_at == cursor_created_at,
                    Message.id < cursor_message_id,
                ),
            )
        )

    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    message_rows = result.all()

    # Reverse to oldest first for UI
    message_rows = message_rows[::-1]
    next_cursor = _encode_message_cursor(message_rows[0][0]) if len(message_rows) == limit else None

    # Mark as read (up to the most recent one we fetched)
    if message_rows:
        await db.execute(
            update(ConversationParticipant)
            .where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == current_user.id,
            )
            .values(last_read_at=datetime.utcnow())
        )
        await db.commit()

    return {
        "messages": [
            _serialize_message(message, from_name=from_name)
            for message, from_name in message_rows
        ],
        "nextCursor": next_cursor
    }

@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse)
async def send_message(
    background_tasks: BackgroundTasks,
    conversation_id: str,
    req: MessageCreateRequest,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    # Verify participation
    p_stmt = select(ConversationParticipant).where(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id
    )
    if not (await db.execute(p_stmt)).scalars().first():
        raise HTTPException(status_code=403, detail="Not a participant")

    participant_ids = await _load_conversation_participant_ids(db, conversation_id)
    media_urls = normalize_media_urls(req.media_urls)
    recipient_ids = [participant_id for participant_id in participant_ids if participant_id != current_user.id]

    new_msg = Message(
        conversation_id=conversation_id,
        from_id=current_user.id,
        text=req.text,
        media_urls=media_urls
    )
    db.add(new_msg)

    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(updated_at=datetime.utcnow())
    )
    await db.commit()
    await db.refresh(new_msg)

    conversation_stmt = select(Conversation).where(Conversation.id == conversation_id)
    conversation = (await db.execute(conversation_stmt)).scalars().first()
    
    # Prepare payload for SSE
    msg_data = {
        "id": new_msg.id,
        "fromId": new_msg.from_id,
        "fromName": current_user.full_name,
        "text": new_msg.text,
        "createdAt": new_msg.created_at.isoformat(),
        "mediaUrls": normalize_media_urls(new_msg.media_urls),
        "readAt": None,
        "conversationId": conversation_id
    }

    background_tasks.add_task(
        _publish_to_users,
        participant_ids,
        "feed:message_new",
        msg_data,
    )

    background_tasks.add_task(
        _send_chat_message_notifications,
        recipient_ids,
        sender_name=current_user.full_name,
        conversation_id=conversation_id,
        message_preview=_build_message_preview(new_msg.text, media_urls),
        group_name=conversation.group_name if conversation and conversation.is_group else None,
    )

    return _serialize_message(new_msg, from_name=current_user.full_name)

@router.delete("/conversations/{conversation_id}/messages/{message_id}")
async def unsend_message(
    background_tasks: BackgroundTasks,
    conversation_id: str,
    message_id: str,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Message).where(
        Message.id == message_id,
        Message.conversation_id == conversation_id
    )
    msg = (await db.execute(stmt)).scalars().first()
    
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
        
    if msg.from_id != current_user.id:
        raise HTTPException(status_code=403, detail="Can only unsend own messages")
        
    if msg.read_at is not None:
        raise HTTPException(status_code=400, detail="Cannot unsend read message")

    participant_ids = await _load_conversation_participant_ids(db, conversation_id)
    await db.delete(msg)
    await db.commit()

    background_tasks.add_task(
        _publish_to_users,
        participant_ids,
        "feed:message_deleted",
        {"conversationId": conversation_id, "messageId": message_id},
    )
        
    return status.HTTP_204_NO_CONTENT

@router.post("/conversations/{conversation_id}/read")
async def mark_read(
    conversation_id: str,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    # Mark all messages in this conversation as read for this user
    # Actually, read receipts are shared. If I read it, 'read_at' is set?
    # Spec says: "Set readAt: null for sender’s messages (deletable until read)"
    # This implies read_at is global per message.
    
    # Mark messages from OTHERS as read
    now = datetime.utcnow()
    await db.execute(
        update(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.from_id != current_user.id,
            Message.read_at == None,
        )
        .values(read_at=now)
    )
    await db.execute(
        update(ConversationParticipant)
        .where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
        .values(last_read_at=now)
    )
    await db.commit()
    
    # Optional: Broadcast "conversation_updated" to sender to show read checkmark
    return {"success": True}

@router.get("/residents", response_model=List[ResidentResponse])
async def search_residents(
    q: Optional[str] = Query(None),
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    """
    Search for residents in the same estate.
    """
    house_search_text = _build_house_search_text()

    stmt = (
        select(User, UserUnit.is_primary, Unit.unit_number, Block.name, Estate.address)
        .outerjoin(UserUnit, UserUnit.user_id == User.id)
        .outerjoin(Unit, UserUnit.unit_id == Unit.id)
        .outerjoin(Block, Unit.block_id == Block.id)
        .outerjoin(Estate, Block.estate_id == Estate.id)
        .where(
            User.estate_id == current_user.estate_id,
            User.id != current_user.id,
            User.is_deleted.is_not(True),
        )
        .order_by(User.full_name.asc(), desc(UserUnit.is_primary), Unit.unit_number.asc())
    )

    if q:
        search_value = q.strip()
        pattern = f"%{search_value}%"
        location_tokens = [token for token in search_value.lower().split() if token]
        location_match = (
            and_(*[house_search_text.like(f"%{token}%") for token in location_tokens])
            if location_tokens
            else None
        )
        stmt = stmt.where(
            or_(
                User.full_name.ilike(pattern),
                User.email.ilike(pattern),
                Unit.unit_number.ilike(pattern),
                Block.name.ilike(pattern),
                Estate.address.ilike(pattern),
                location_match,
            )
        )

    stmt = stmt.limit(100)
    rows = (await db.execute(stmt)).all()

    residents_by_id: dict[str, dict[str, Optional[str]]] = {}
    for resident, is_primary, unit_number, block_name, estate_address in rows:
        unit_label = _build_house_label(unit_number, block_name)

        current = residents_by_id.get(resident.id)
        if current is None or (
            unit_label and not current["unit"]
        ) or (
            is_primary and current["unit"] != unit_label
        ):
            residents_by_id[resident.id] = {
                "id": resident.id,
                "name": resident.full_name,
                "avatar": resident.profile_image_url,
                "unit": unit_label,
            }

    return list(residents_by_id.values())


@router.get("/residents/grouped", response_model=List[ResidentHouseGroupResponse])
async def search_residents_grouped(
    q: Optional[str] = Query(None),
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    """
    Search for houses in the same estate and return residents grouped by house.
    """
    house_search_text = _build_house_search_text()
    stmt = (
        select(
            User,
            UserUnit.unit_id,
            UserUnit.is_primary,
            Unit.unit_number,
            Block.name,
            Estate.address,
        )
        .outerjoin(UserUnit, UserUnit.user_id == User.id)
        .outerjoin(Unit, UserUnit.unit_id == Unit.id)
        .outerjoin(Block, Unit.block_id == Block.id)
        .outerjoin(Estate, Block.estate_id == Estate.id)
        .where(
            User.estate_id == current_user.estate_id,
            User.id != current_user.id,
            User.is_deleted.is_not(True),
        )
        .order_by(
            Unit.unit_number.asc(),
            Block.name.asc(),
            desc(UserUnit.is_primary),
            User.full_name.asc(),
        )
    )

    if q:
        search_value = q.strip()
        pattern = f"%{search_value}%"
        location_tokens = [token for token in search_value.lower().split() if token]
        location_match = (
            and_(*[house_search_text.like(f"%{token}%") for token in location_tokens])
            if location_tokens
            else None
        )
        stmt = stmt.where(
            or_(
                User.full_name.ilike(pattern),
                User.email.ilike(pattern),
                Unit.unit_number.ilike(pattern),
                Block.name.ilike(pattern),
                Estate.address.ilike(pattern),
                location_match,
            )
        )

    matched_rows = (await db.execute(stmt.limit(200))).all()
    matched_unit_ids = {unit_id for _, unit_id, _, _, _, _ in matched_rows if unit_id}
    if not matched_unit_ids:
        return []

    residents_stmt = (
        select(
            User,
            UserUnit.unit_id,
            UserUnit.is_primary,
            Unit.unit_number,
            Block.name,
            Estate.address,
        )
        .join(UserUnit, UserUnit.user_id == User.id)
        .join(Unit, UserUnit.unit_id == Unit.id)
        .join(Block, Unit.block_id == Block.id)
        .join(Estate, Block.estate_id == Estate.id)
        .where(
            User.estate_id == current_user.estate_id,
            User.id != current_user.id,
            User.is_deleted.is_not(True),
            UserUnit.unit_id.in_(matched_unit_ids),
        )
        .order_by(
            Unit.unit_number.asc(),
            Block.name.asc(),
            desc(UserUnit.is_primary),
            User.full_name.asc(),
        )
    )
    resident_rows = (await db.execute(residents_stmt)).all()

    grouped: dict[str, dict[str, Any]] = {}
    for resident, unit_id, is_primary, unit_number, block_name, estate_address in resident_rows:
        house_label = _build_house_label(unit_number, block_name)
        group = grouped.setdefault(
            unit_id,
            {
                "unitId": unit_id,
                "houseLabel": house_label,
                "blockName": block_name,
                "estateAddress": estate_address,
                "residents": [],
                "_seen": set(),
            },
        )
        if resident.id in group["_seen"]:
            continue
        group["_seen"].add(resident.id)
        group["residents"].append(
            {
                "id": resident.id,
                "name": resident.full_name,
                "avatar": resident.profile_image_url,
                "unit": house_label,
            }
        )

    results = list(grouped.values())
    for group in results:
        group.pop("_seen", None)
    return results

# Helper
async def get_single_conversation_enriched(conv_id: str, user_id: str, db: AsyncSession):
    stmt = select(Conversation).where(Conversation.id == conv_id)
    conv = (await db.execute(stmt)).scalars().first()

    participants_map = await _load_conversation_participants(db, [conv_id])
    return {
        "id": conv.id,
        "participants": participants_map.get(conv_id, []),
        "isGroup": conv.is_group,
        "unreadCount": 0,
        "groupName": conv.group_name
    }
