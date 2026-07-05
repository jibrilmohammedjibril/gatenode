from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from core.db import get_db
from core.models import Estate
from schemas import EstateBrandingResponse

router = APIRouter(prefix="/public", tags=["Public"])

@router.get("/estate-branding/{estate_id}", response_model=EstateBrandingResponse)
async def get_estate_branding(
    estate_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get public branding info for an estate.
    Used for the login screen.
    """
    result = await db.execute(select(Estate).where(Estate.id == estate_id))
    estate = result.scalars().first()
    
    if not estate:
        # Don't return 404 to avoid enumeration? 
        # Requirement says "If estate doesn't exist... return 404 or a response with has_custom_logo: false"
        # Let's return a default object with has_custom_logo=False to be safe and friendly.
        # But commonly 404 is fine for IDs. Let's stick to 404 for invalid ID, 
        # or just return default if ID is valid format but not found?
        # Specification: "If the estate doesn't exist ... return 404"
        raise HTTPException(status_code=404, detail="Estate not found")

    # In a real scenario, we'd check if estate has branding config.
    # For MVP, we check if logo_url is set.
    
    has_custom = bool(estate.logo_url)
    
    return {
        "estate_id": estate.id,
        "estate_name": estate.name,
        "logo_url": estate.logo_url,
        "has_custom_logo": has_custom,
        "primary_color": "#1E40AF", # Default or from DB if added later
        "secondary_color": "#3B82F6" # Default
    }
