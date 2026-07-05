from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from core.db import get_db
from core.models import User, Estate
from core.deps import require_estate_membership
from schemas import HomeConfigResponse, QuickAction
from typing import Optional, List

router = APIRouter(prefix="/config", tags=["Config"])

@router.get("/home", response_model=HomeConfigResponse)
async def get_home_config(
    x_estate_id: Optional[str] = Header(None, alias="X-Estate-ID"),
    x_unit_id: Optional[str] = Header(None, alias="X-Unit-ID"),
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    """
    Get home screen configuration (e.g. Invite Visitor button).
    """
    # Fetch Estate config
    # Use current_user.estate_id as the source of truth for the user's estate context
    stmt = select(Estate).where(Estate.id == current_user.estate_id)
    result = await db.execute(stmt)
    estate = result.scalars().first()
    
    if estate and estate.home_config:
        config_data = estate.home_config
        # Basic validation: ensure quickActions exists
        if isinstance(config_data, dict) and "quickActions" in config_data:
             return config_data
             
    # Default Configuration
    # Fallback if no specific config is set in DB
    return {
        "quickActions": [
            {
                "id": "invite",
                "label": "Invite Visitor",
                "route": "/invite",
                "enabled": True,
                # animationUrl omitted to use app default
            }
        ]
    }
