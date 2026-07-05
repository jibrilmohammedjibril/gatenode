
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from core.db import get_db
from core.notifications import notifications
import logging

router = APIRouter(prefix="/webhooks/chatwoot", tags=["Webhooks"])
logger = logging.getLogger(__name__)

@router.post("")
async def chatwoot_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
        
    event = payload.get("event")
    msg_type = payload.get("message_type")
    
    # We only care about outgoing messages (Agent -> User)
    if event == "message_created" and msg_type == "outgoing":
        content = payload.get("content", "")
        conversation = payload.get("conversation", {})
        contact_inbox = conversation.get("contact_inbox", {})
        source_id = contact_inbox.get("source_id") # This should be our User ID
        conversation_id = str(conversation.get("id"))
        
        if source_id:
            logger.info(f"Received Chatwoot reply for User {source_id}")
            
            # Truncate content for preview
            preview = (content[:100] + '...') if len(content) > 100 else content
            
            await notifications.send_support_reply(
                db=db,
                user_id=source_id,
                message_preview=preview,
                conversation_id=conversation_id
            )
            
    return {"status": "ok"}
