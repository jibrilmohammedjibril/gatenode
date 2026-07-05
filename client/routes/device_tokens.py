from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from core.db import get_db
from core.models import User, DeviceToken
from core.deps import get_current_user
from pydantic import BaseModel

router = APIRouter(prefix="/device-tokens", tags=["Device Tokens"])

class DeviceTokenRequest(BaseModel):
    token: str
    platform: str = "ios"

@router.post("/", response_model=dict)
async def register_device_token(
    data: DeviceTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Register a push notification token.
    """
    print(f"DEBUG: Incoming Device Token Payload: {data.model_dump()}")
    
    if not data.token or data.token.lower() in ["string", "test", "null", "undefined"] or len(data.token) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid device token provided"
        )
        
    # Check if token exists globally? Or just for this user?
    # Tokens are unique to devices. A device might change users?
    # If token exists for ANOTHER user, we should probably steal it or delete old one.
    # Exponent tokens are unique per app/device.
    
    # 1. Clear exactly matching tokens to prevent notification leaks if device changes hands
    await db.execute(delete(DeviceToken).where(DeviceToken.token == data.token))
    
    # 2. Clear any old tokens for THIS user, guaranteeing exactly 1 active token maximum
    await db.execute(delete(DeviceToken).where(DeviceToken.user_id == current_user.id))
    
    # 3. Insert the single new token
    new_token = DeviceToken(
        token=data.token,
        platform=data.platform,
        user_id=current_user.id,
        active_token_id=current_user.active_token_id
    )
    db.add(new_token)
        
    await db.commit()
    
    return {"success": True, "message": "Device token registered successfully"}
