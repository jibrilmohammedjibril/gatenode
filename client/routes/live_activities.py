"""
Live Activities API endpoints for iOS Dynamic Island integration.
Handles ActivityKit push token registration.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime

from core.db import get_db
from core.models import User, LiveActivityToken, VisitorInvite
from core.deps import set_tenant_context

router = APIRouter(tags=["Live Activities"])

class ActivityTokenRequest(BaseModel):
    activity_id: str = Field(..., alias="activityId")
    invite_id: str = Field(..., alias="inviteId")
    activity_push_token: str = Field(..., alias="activityPushToken")
    received_at: str = Field(..., alias="receivedAt")
    
    class Config:
        populate_by_name = True

@router.post("/tokens")
async def register_activity_token(
    data: ActivityTokenRequest,
    current_user: User = Depends(set_tenant_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Register or update an ActivityKit push token for a Live Activity.
    
    Tokens can rotate, so we store the latest one per activity_id.
    The iOS app sends this when a Live Activity starts.
    """
    # Verify invite belongs to user
    invite = await db.get(VisitorInvite, data.invite_id)
    if not invite or invite.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Invite not found")
    
    # Check if activity already exists
    existing_query = await db.execute(
        select(LiveActivityToken).where(
            LiveActivityToken.activity_id == data.activity_id
        )
    )
    token_record = existing_query.scalar_one_or_none()
    
    if token_record:
        # Update existing token (token rotation)
        token_record.activity_push_token = data.activity_push_token
        token_record.updated_at = datetime.utcnow()
        print(f"🔄 Updated Live Activity token: {data.activity_id[:8]}...")
    else:
        # Create new token record
        token_record = LiveActivityToken(
            activity_id=data.activity_id,
            invite_id=data.invite_id,
            user_id=current_user.id,
            activity_push_token=data.activity_push_token
        )
        db.add(token_record)
        print(f"✅ Registered new Live Activity token: {data.activity_id[:8]}...")
    
    await db.commit()
    
    return {
        "message": "Activity token registered",
        "activityId": data.activity_id
    }
