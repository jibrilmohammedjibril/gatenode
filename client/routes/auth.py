import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from sqlalchemy.orm import selectinload

from core.db import get_db
from core.deps import get_current_user
from core.models import (
    User,
    Unit,
    UserUnit,
    Block,
    Estate,
    UserRole,
    HouseholdRole,
    OTPCode,
    DeviceToken,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
    build_full_name,
    normalize_email,
)
from core.security import get_password_hash, verify_password, create_access_token, create_refresh_token, verify_token
from core.mail import send_email_async
from core.otp_hardening import can_issue_otp, get_otp_request_metadata
from core.rate_limit import limiter, RateLimits
from schemas import (
    ClientSignup,
    ClientLoginV,
    ClientTokenResponse,
    ClientRefreshToken,
    EstateJoinRequest,
    EstateJoinResponse,
    PasswordResetRequest,
    PasswordResetConfirm,
)
from datetime import datetime, timedelta, timezone
import secrets
import string
import uuid

router = APIRouter(prefix="/auth", tags=["Auth"])
logger = logging.getLogger(__name__)


def _resolved_user_names(user: User) -> dict[str, str | None]:
    if user.first_name or user.middle_name or user.last_name:
        return {
            "first_name": user.first_name,
            "middle_name": user.middle_name,
            "last_name": user.last_name,
        }

    parts = [part for part in (user.full_name or "").split() if part]
    if not parts:
        return {"first_name": None, "middle_name": None, "last_name": None}
    if len(parts) == 1:
        return {"first_name": parts[0], "middle_name": None, "last_name": parts[0]}
    if len(parts) == 2:
        return {"first_name": parts[0], "middle_name": None, "last_name": parts[1]}
    return {
        "first_name": parts[0],
        "middle_name": " ".join(parts[1:-1]),
        "last_name": parts[-1],
    }


async def _resolve_user_context(
    db: AsyncSession,
    user: User,
    *,
    allow_missing_estate: bool = True,
) -> dict[str, str | bool | None]:
    stmt = (
        select(UserUnit, Unit, Block)
        .join(Unit, UserUnit.unit_id == Unit.id)
        .join(Block, Unit.block_id == Block.id)
        .where(UserUnit.user_id == user.id)
        .order_by(UserUnit.is_primary.desc())
    )
    row = (await db.execute(stmt)).first()

    unit_id = None
    is_household_admin = False
    resolved_estate_id = user.estate_id

    estate_id_updated = False
    if row:
        link, unit, block = row
        unit_id = unit.id
        is_household_admin = link.role in [HouseholdRole.ADMIN, HouseholdRole.SUB_ADMIN]
        if not resolved_estate_id:
            resolved_estate_id = block.estate_id

    if not resolved_estate_id:
        if allow_missing_estate:
            return {
                "estate_id": None,
                "unit_id": None,
                "is_household_admin": False,
                "estate_id_updated": False,
            }
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is not linked to an estate",
        )

    if user.estate_id != resolved_estate_id:
        user.estate_id = resolved_estate_id
        db.add(user)
        estate_id_updated = True

    return {
        "estate_id": resolved_estate_id,
        "unit_id": unit_id,
        "is_household_admin": is_household_admin,
        "estate_id_updated": estate_id_updated,
    }

async def _ensure_subscription(db: AsyncSession, user: User) -> None:
    stmt_sub = select(Subscription).where(Subscription.user_id == user.id)
    existing_sub = (await db.execute(stmt_sub)).scalars().first()

    if existing_sub:
        return

    new_sub = Subscription(
        user_id=user.id,
        plan=SubscriptionPlan.PREMIUM,
        status=SubscriptionStatus.ACTIVE,
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=36500),
        auto_renew=False,
    )
    db.add(new_sub)


def _build_token_response(user: User, token: str, refresh_token: str, context: dict[str, str | bool | None]) -> dict:
    name_parts = _resolved_user_names(user)
    return {
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user_id": user.id,
        "full_name": user.full_name,
        "first_name": name_parts["first_name"],
        "middle_name": name_parts["middle_name"],
        "last_name": name_parts["last_name"],
        "estate_id": context["estate_id"],
        "unit_id": context["unit_id"],
        "is_household_admin": context["is_household_admin"],
    }


@router.post("/signup", response_model=ClientTokenResponse)
@limiter.limit(RateLimits.AUTH)
async def client_signup(request: Request, data: ClientSignup, db: AsyncSession = Depends(get_db)):
    normalized_email = normalize_email(data.email)
    existing = await db.execute(select(User).where(User.email == normalized_email))
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    full_name = build_full_name(data.first_name, data.middle_name, data.last_name)
    if not full_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="first_name and last_name are required")

    user = User(
        email=normalized_email,
        hashed_password=get_password_hash(data.password),
        full_name=full_name,
        first_name=data.first_name.strip(),
        middle_name=data.middle_name.strip() if data.middle_name else None,
        last_name=data.last_name.strip(),
        phone_number=data.phone_number.strip() if data.phone_number else None,
        role=UserRole.RESIDENT,
        estate_id=None,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    await _ensure_subscription(db, user)

    token_id = str(uuid.uuid4())
    user.active_token_id = token_id
    db.add(user)
    await db.commit()
    await db.refresh(user)

    context = await _resolve_user_context(db, user)
    token = create_access_token(subject=user.id, token_id=token_id)
    refresh_token = create_refresh_token(subject=user.id, token_id=token_id)
    return _build_token_response(user, token, refresh_token, context)


@router.post("/join-estate", response_model=EstateJoinResponse)
@limiter.limit(RateLimits.AUTH)
async def join_estate(
    request: Request,
    data: EstateJoinRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    code = data.estate_code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="estateCode is required")

    stmt = (
        select(Unit, Block, Estate)
        .join(Block, Unit.block_id == Block.id)
        .join(Estate, Block.estate_id == Estate.id)
        .where(Unit.access_code == code)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Estate code not found")

    unit, block, estate = row

    if current_user.estate_id and current_user.estate_id != estate.id:
        raise HTTPException(status_code=409, detail="Account is already linked to a different estate")

    existing_link = (
        await db.execute(
            select(UserUnit).where(
                UserUnit.user_id == current_user.id,
                UserUnit.unit_id == unit.id,
            )
        )
    ).scalars().first()

    all_links = (
        await db.execute(select(UserUnit).where(UserUnit.user_id == current_user.id))
    ).scalars().all()

    is_primary = not all_links
    if existing_link:
        existing_link.is_primary = True if is_primary else existing_link.is_primary
        link = existing_link
    else:
        link = UserUnit(
            user_id=current_user.id,
            unit_id=unit.id,
            is_primary=is_primary,
            role=HouseholdRole.ADMIN if is_primary else HouseholdRole.OTHER,
        )
        db.add(link)

    current_user.estate_id = estate.id
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    return {
        "estateId": estate.id,
        "estateName": estate.name,
        "unitId": unit.id,
        "unitNumber": unit.unit_number,
        "blockName": block.name,
        "isPrimary": link.is_primary,
        "message": "Estate joined successfully",
    }


@router.post("/leave-estate")
@limiter.limit(RateLimits.AUTH)
async def leave_estate(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(UserUnit).where(UserUnit.user_id == current_user.id))
    current_user.estate_id = None
    db.add(current_user)
    await db.commit()

    return {"message": "Estate left successfully"}

@router.post("/login", response_model=ClientTokenResponse)
@limiter.limit(RateLimits.AUTH)
async def login(request: Request, data: ClientLoginV, db: AsyncSession = Depends(get_db)):
    email = normalize_email(data.email)
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect credentials"
        )
    
    if user.role != UserRole.RESIDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client app access is limited to residents",
        )
        
    # Reactivate soft-deleted account
    if user.deletion_requested_at:
        user.deletion_requested_at = None
        db.add(user)
        await db.commit() 

    # Session Tracking
    import uuid
    token_id = str(uuid.uuid4())
    user.active_token_id = token_id
    context = await _resolve_user_context(db, user)
    db.add(user)

    # Device Token Registration
    if data.device_token:
        # 1. Clear exactly matching tokens to prevent notification leaks if device changes hands
        await db.execute(delete(DeviceToken).where(DeviceToken.token == data.device_token))
        
        # 2. Clear any old tokens for THIS user, guaranteeing exactly 1 active token maximum
        await db.execute(delete(DeviceToken).where(DeviceToken.user_id == user.id))
        
        # 3. Insert the single new token
        new_dt = DeviceToken(
            token=data.device_token,
            platform=data.platform or "ios",
            user_id=user.id,
            active_token_id=token_id # Link to Session
        )
        db.add(new_dt)
    
    await db.commit()

    token = create_access_token(subject=user.id, token_id=token_id)
    refresh_token = create_refresh_token(subject=user.id, token_id=token_id)
    name_parts = _resolved_user_names(user)
    
    return _build_token_response(user, token, refresh_token, context)



@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """
    OAuth2 compatible token login, used for Swagger UI.
    """
    email = normalize_email(form_data.username)
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Reactivate soft-deleted account
    if user.deletion_requested_at:
        user.deletion_requested_at = None
        db.add(user)
        await db.commit()
        
    # Session Tracking
    import uuid
    token_id = str(uuid.uuid4())
    user.active_token_id = token_id
    db.add(user)
    await db.commit()

    token = create_access_token(subject=user.id, token_id=token_id)
    return {"access_token": token, "token_type": "bearer"}

@router.post("/refresh", response_model=ClientTokenResponse)
@limiter.limit(RateLimits.STANDARD)
async def refresh_token(request: Request, data: ClientRefreshToken, db: AsyncSession = Depends(get_db)):
    refresh_token = data.refresh_token
    try:
        payload = verify_token(refresh_token)
        if not payload.get("refresh"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        user_id = payload.get("sub")
        # Extract Token ID from Refresh Token
        incoming_token_id = payload.get("tid")
        
        if user_id is None:
             raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
        
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
        
    # Enforce Single Device Login on Refresh
    # If the user has an active session in DB, this refresh token MUST match it.
    if user.active_token_id:
        if incoming_token_id != user.active_token_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired (Logged in on another device)"
            )
    else:
        # If DB is empty (migration case), we proceed and will set it below.
        pass

    # Relaxed Rotation: Do NOT rotate session ID on refresh.
    # This prevents race conditions where a retry fails because the first request rotated it.
    # Security is maintained because we still validate 'user.active_token_id'.
    
    new_access_token = create_access_token(subject=user.id, token_id=incoming_token_id)
    new_refresh_token = create_refresh_token(subject=user.id, token_id=incoming_token_id)
    name_parts = _resolved_user_names(user)
    context = await _resolve_user_context(db, user)
    if context["estate_id_updated"]:
        await db.commit()
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token, # Return NEW refresh token (with same session ID)
        "token_type": "bearer",
        "user_id": user.id,
        "full_name": user.full_name,
        "first_name": name_parts["first_name"],
        "middle_name": name_parts["middle_name"],
        "last_name": name_parts["last_name"],
        "estate_id": context["estate_id"],
        "unit_id": context["unit_id"],
        "is_household_admin": context["is_household_admin"],

    }

@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Logout the current user and clear session.
    Stateless JWTs remain valid until expiry, but clearing active_token_id
    prevents push notifications and refresh tokens from working.
    """
    current_user.active_token_id = None
    db.add(current_user)
    await db.commit()
    
    return {"message": "Logged out successfully"}

@router.post("/request-password-reset")
@limiter.limit(RateLimits.AUTH)
async def request_password_reset(request: Request, data: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    # 1. Check if user exists (silently)
    email = normalize_email(data.email)
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    
    if user:
        if not await can_issue_otp(db, email=email, otp_type="reset", reveal_limit=False):
            return {
                "message": "If an account exists with this email, you will receive a password reset code.",
                "otp_sent": True
            }

        # 2. Generate OTP
        otp_code = ''.join(secrets.choice(string.digits) for _ in range(6))
        
        # 3. Store OTP
        otp = OTPCode(
            email=email,
            code=otp_code,
            type="reset",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            **get_otp_request_metadata(request),
        )
        db.add(otp)
        await db.commit()
        
        # 4. Send Email
        try:
             await send_email_async(
                email_to=email,
                subject="Password Reset Request",
                title="Password Reset",
                body_text="Your password reset code is below. It expires in 15 minutes.",
                access_code=otp_code,
                sender_name=f"Resident Client ({otp_code})"
             )
        except Exception as e:
            logger.warning("Failed to send password reset email for %s", email, exc_info=True)

    return {
        "message": "If an account exists with this email, you will receive a password reset code.",
        "otp_sent": True
    }

@router.post("/reset-password")
@limiter.limit(RateLimits.AUTH)
async def reset_password(request: Request, data: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    # 1. Verify OTP
    email = normalize_email(data.email)
    stmt = select(OTPCode).where(
        OTPCode.email == email,
        OTPCode.code == data.otp,
        OTPCode.type == "reset",
        OTPCode.used == False,
        OTPCode.expires_at > datetime.now(timezone.utc)
    )
    result = await db.execute(stmt)
    otp_record = result.scalars().first()
    
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
        
    # 2. Get User
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # 3. Update Password
    user.hashed_password = get_password_hash(data.new_password)
    
    # 4. Mark OTP used
    otp_record.used = True
    
    db.add(user)
    db.add(otp_record)
    await db.commit()
    
    return {
        "message": "Password successfully reset",
        "success": True
    }
