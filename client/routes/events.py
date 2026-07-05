from fastapi import APIRouter, Depends, Request, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.db import get_db
from sse_starlette.sse import EventSourceResponse
from core.deps import get_current_user
from core.models import User
from core.events import event_manager
import asyncio
import json
from datetime import datetime, timezone

router = APIRouter()

@router.get("/events")
async def sse_events(
    request: Request,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Server-Sent Events for real-time updates.
    """
    # 1. Authenticate (Query Param)
    try:
        from core.security import verify_token
        from core.deps import get_current_user
        from sqlalchemy.future import select
        
        payload = verify_token(token)
        user_id = payload.get("sub")
        if not user_id:
             # Standard EventSource doesn't handle 401 well, but we must reject.
             # Returning strict error.
             raise HTTPException(status_code=401, detail="Invalid token")
             
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        current_user = result.scalars().first()
        
        if not current_user:
            raise HTTPException(status_code=401, detail="User not found")
            
    except Exception as e:
        # Log error?
        raise HTTPException(status_code=401, detail="Authentication failed")

    async def event_generator():
        # Subscribe
        queue = await event_manager.subscribe(current_user.id)
        
        try:
            while True:
                # Wait for event OR heartbeat
                try:
                    # Wait for message with timeout for heartbeat
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {
                        "event": message["event"],
                        "data": json.dumps(message["data"])
                    }
                except asyncio.TimeoutError:
                    # Heartbeat
                    yield {
                        "event": "ping",
                        "data": json.dumps({
                            "timestamp": datetime.utcnow().isoformat()
                        })
                    }
                    
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                    
        except asyncio.CancelledError:
            pass
        finally:
            await event_manager.unsubscribe(current_user.id, queue)

    return EventSourceResponse(event_generator())

@router.post("/events/debug/trigger")
async def trigger_debug_event(
    current_user: User = Depends(get_current_user)
):
    await event_manager.publish("debug:test", {"message": "Hello World", "timestamp": datetime.utcnow().isoformat()}, current_user.id)
    return {"message": "debug:test event triggered"}

@router.post("/events/debug/trigger-wallet")
async def trigger_wallet_event(
    current_user: User = Depends(get_current_user)
):
    """Simulate a wallet:balance_updated SSE event (for testing only)."""
    await event_manager.publish("wallet:balance_updated", {
        "new_balance": 500.0,
        "change_amount": 50.0,
        "change_type": "debit",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }, current_user.id)
    return {"message": "wallet:balance_updated event triggered"}

@router.post("/events/debug/trigger-notification")
async def trigger_notification_event(
    current_user: User = Depends(get_current_user)
):
    """Simulate a notification SSE event (for testing only)."""
    await event_manager.publish("notification", {
        "title": "Test Notification",
        "message": "This is a test notification from the SSE debug endpoint."
    }, current_user.id)
    return {"message": "notification event triggered"}
