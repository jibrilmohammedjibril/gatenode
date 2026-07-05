from fastapi import Depends, HTTPException, Header, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional

from core.db import get_db
from core.models import User, UserRole, Subscription, SubscriptionStatus, SubscriptionPlan, UserUnit, Unit
from core.security import verify_token

# Specific to Client API
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: AsyncSession = Depends(get_db)
) -> User:
    try:
        payload = verify_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.role != UserRole.RESIDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Client app access is limited to residents")
        
    # Enforce Single Device Login
    token_id = payload.get("tid")
    
    if user.active_token_id:
        # If DB has a session ID, token MUST match it.
        # Note: If token has NO tid (old token), it will be None. None != "xyz" -> mismatch -> 401. Correct.
        if token_id != user.active_token_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Session expired (Logged in on another device)"
            )
        
    return user


async def require_estate_membership(
    user: User = Depends(get_current_user),
) -> User:
    if not user.estate_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Join an estate to continue",
        )
    return user

async def get_current_unit_id(x_unit_id: Optional[str] = Header(None)) -> Optional[str]:
    return x_unit_id

async def get_current_unit(
    unit_id: Optional[str] = Depends(get_current_unit_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Unit:
    """
    Validates that the provided X-Unit-ID belongs to the user.
    If no header is provided, tries to find a Primary unit.
    """
    if not user.estate_id:
        raise HTTPException(status_code=409, detail="Join an estate to continue")

    if unit_id:
        # Verify ownership/access
        stmt = select(UserUnit).where(UserUnit.user_id == user.id, UserUnit.unit_id == unit_id)
        result = await db.execute(stmt)
        uu = result.scalars().first()
        if not uu:
            raise HTTPException(status_code=403, detail="Access to this unit denied")
        
        # Fetch actual Unit object
        unit_res = await db.execute(select(Unit).where(Unit.id == unit_id))
        unit = unit_res.scalars().first()
        return unit
    
    # Fallback: Try primary
    stmt = select(UserUnit).where(UserUnit.user_id == user.id, UserUnit.is_primary == True)
    result = await db.execute(stmt)
    uu = result.scalars().first()
    if uu:
        unit_res = await db.execute(select(Unit).where(Unit.id == uu.unit_id))
        return unit_res.scalars().first()
        
    raise HTTPException(status_code=409, detail="Join an estate to continue")


async def get_optional_unit(
    unit_id: Optional[str] = Depends(get_current_unit_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Optional[Unit]:
    if not user.estate_id:
        return None

    if unit_id:
        stmt = select(UserUnit).where(UserUnit.user_id == user.id, UserUnit.unit_id == unit_id)
        result = await db.execute(stmt)
        uu = result.scalars().first()
        if not uu:
            raise HTTPException(status_code=403, detail="Access to this unit denied")

        unit_res = await db.execute(select(Unit).where(Unit.id == unit_id))
        return unit_res.scalars().first()

    stmt = select(UserUnit).where(UserUnit.user_id == user.id, UserUnit.is_primary == True)
    result = await db.execute(stmt)
    uu = result.scalars().first()
    if uu:
        unit_res = await db.execute(select(Unit).where(Unit.id == uu.unit_id))
        return unit_res.scalars().first()

    return None

def require_role(role: UserRole):
    async def dependency(user: User = Depends(get_current_user)):
        if user.role != role and user.role != UserRole.SUPER_ADMIN:
            raise HTTPException(status_code=403, detail="Not authorized")
        return user
    return dependency

async def require_active_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency to check if user has an active PREMIUM subscription.
    """
    stmt = select(Subscription).where(Subscription.user_id == user.id)
    result = await db.execute(stmt)
    sub = result.scalars().first()
    
    if not sub:
        # No sub record = assume Basic = Forbidden for premium features
        raise HTTPException(status_code=403, detail="Active Premium Subscription required")
        
    if sub.status != SubscriptionStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Subscription expired")
        
    if sub.plan != SubscriptionPlan.PREMIUM:
        raise HTTPException(status_code=403, detail="Premium plan required")
        
    return user

async def set_tenant_context(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Sets the current_estate_id in PostgreSQL session/transaction configuration.
    This is required for RLS Policies to work.
    """
    from sqlalchemy import text
    if not user.estate_id:
        return user
    try:
        # set_config(key, value, is_local). is_local=True -> scoped to transaction
        await db.execute(text(f"SELECT set_config('app.current_estate_id', '{user.estate_id}', true)"))
    except Exception as e:
        print(f"RLS Context Set Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Security Error")
        
    return user
