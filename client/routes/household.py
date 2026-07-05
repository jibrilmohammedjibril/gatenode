from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from core.db import get_db
from core.models import User, UserUnit, Unit, HouseholdInvite, InviteStatus, Estate, UserRole, HouseholdRole, build_full_name, normalize_email
from core.deps import get_current_user, get_current_unit, require_estate_membership, set_tenant_context
from schemas import HouseholdMemberResponse, HouseholdCodeResponse, HouseholdAddRequest
from core.mail import send_email_async
from core.notifications import notifications

router = APIRouter(prefix="/household", tags=["Household"])


def _resolve_name_fields(
    *,
    first_name: str,
    middle_name: str | None,
    last_name: str,
) -> tuple[str, str | None, str | None, str | None]:
    first = first_name.strip() if first_name else None
    middle = middle_name.strip() if middle_name else None
    last = last_name.strip() if last_name else None

    if not first or not last:
        raise HTTPException(status_code=400, detail="first_name and last_name are required")

    return build_full_name(first, middle, last), first, middle, last

@router.get("", response_model=list[HouseholdMemberResponse])
async def list_household_members(
    current_user: User = Depends(require_estate_membership),
    unit = Depends(get_current_unit), # Mandatory
    db: AsyncSession = Depends(get_db)
):
    if not unit:
        raise HTTPException(status_code=400, detail="Unit context required")
        
    result = await db.execute(
        select(UserUnit)
        .options(selectinload(UserUnit.user))
        .where(UserUnit.unit_id == unit.id)
    )
    unites = result.scalars().all()
    
    members = []
    for link in unites:
        user = link.user
        # Use DB role or fallback
        if link.role:
            role_display = link.role.value.capitalize()
        else:
            role_display = "Admin" if link.is_primary else "Other"
        
        members.append({
            "user_id": user.id,
            "full_name": user.full_name,
            "role": role_display,
            "phone_number": user.phone_number,
            "email": user.email,
            "profile_image_url": user.profile_image_url
        })
        
    return members

@router.post("", response_model=dict)
async def add_member(
    data: HouseholdAddRequest,
    current_user: User = Depends(require_estate_membership),
    unit = Depends(get_current_unit),
    db: AsyncSession = Depends(get_db)
):
    if not unit:
         raise HTTPException(status_code=400, detail="Unit context required")

    # 1. Verify Inviter is ADMIN
    from core.models import HouseholdRole
    
    stmt_role = select(UserUnit).where(UserUnit.user_id == current_user.id, UserUnit.unit_id == unit.id)
    res_role = await db.execute(stmt_role)
    inviter_link = res_role.scalars().first()
    
    if not inviter_link or inviter_link.role not in [HouseholdRole.ADMIN, HouseholdRole.SUB_ADMIN]:
        raise HTTPException(status_code=403, detail="Only the Household Admin can invite members")
         
    # Check if user exists
    normalized_email = normalize_email(data.email)
    stmt = select(User).where(User.email == normalized_email)
    res = await db.execute(stmt)
    existing_user = res.scalars().first()
    
    # Resolve Target Role
    try:
        target_role = HouseholdRole(data.role.lower())
    except ValueError:
        target_role = HouseholdRole.OTHER # Specific fallback
    
    access_code_to_send = None
    
    if existing_user:
        # Check if already linked to this unit
        stmt_link = select(UserUnit).where(UserUnit.user_id == existing_user.id, UserUnit.unit_id == unit.id)
        res_link = await db.execute(stmt_link)
        if res_link.scalars().first():
            raise HTTPException(status_code=409, detail="Member already exists in household")
            
        # Link existing user
        link = UserUnit(
            user_id=existing_user.id,
            unit_id=unit.id,
            is_primary=False,
            role=target_role
        )
        db.add(link)
        
        # If they have an access_code (not onboarded yet), resend it
        access_code_to_send = existing_user.access_code
        
    else:
        # Create new User
        import secrets
        from core.security import get_password_hash
        from core.models import generate_access_code
        
        random_pw = secrets.token_urlsafe(16)
        new_access_code = generate_access_code(8)
        full_name, first_name, middle_name, last_name = _resolve_name_fields(
            first_name=data.first_name,
            middle_name=data.middle_name,
            last_name=data.last_name,
        )
        
        existing_user = User(
            email=normalized_email,
            full_name=full_name,
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            hashed_password=get_password_hash(random_pw),
            role=UserRole.RESIDENT,
            estate_id=current_user.estate_id,
            phone_number=None,
            is_active=True,
            access_code=new_access_code,
            profile_image_url=data.profile_image_url,
            wallet_balance=0 # New User starts with 0
        )
        db.add(existing_user)
        await db.flush() # Get ID
        
        # Link
        link = UserUnit(
            user_id=existing_user.id,
            unit_id=unit.id,
            is_primary=True, # First unit?
            role=target_role
        )
        db.add(link)
        
        access_code_to_send = new_access_code

    await db.commit()

    # Send Email
    # Fetch Estate Name for Location
    stmt_estate = select(Estate).where(Estate.id == current_user.estate_id)
    res_estate = await db.execute(stmt_estate)
    estate_obj = res_estate.scalars().first()
    location_name = estate_obj.name if estate_obj else "Resident Estate"
    
    # Body Text
    if access_code_to_send:
        body_text = f"<strong>{current_user.full_name}</strong> has invited you to join the <strong>{unit.unit_number}</strong> household in <strong>{location_name}</strong>. Use the secure access code below to get started."
    else:
        body_text = f"<strong>{current_user.full_name}</strong> has invited you to join the <strong>{unit.unit_number}</strong> household in <strong>{location_name}</strong>. Please log in to your account to view your new household."

    await send_email_async(
        email_to=normalized_email,
        subject="Welcome home!",
        title="Welcome home!",
        body_text=body_text,
        access_code=access_code_to_send
    )
    
    # Notify if already exists (Push)
    if existing_user: # It always exists now
         await notifications.send_added_to_household(
            db=db,
            user_id=existing_user.id,
            unit_number=unit.unit_number,
            house_id=unit.id
         )
    
    return {"message": f"Member added and notified: {normalized_email}"}

@router.post("/invite", response_model=dict)
async def add_member_alias(
    data: HouseholdAddRequest,
    current_user: User = Depends(require_estate_membership),
    unit = Depends(get_current_unit),
    db: AsyncSession = Depends(get_db)
):
    """Alias for POST /household to match specific requirement."""
    return await add_member(data, current_user, unit, db)

@router.delete("/{target_user_id}")
async def remove_member(
    target_user_id: str,
    current_user: User = Depends(require_estate_membership),
    unit = Depends(get_current_unit),
    db: AsyncSession = Depends(get_db)
):
    if not unit:
        raise HTTPException(status_code=400, detail="Unit context required")
        
    # Check Target
    stmt_target = select(UserUnit).where(UserUnit.user_id == target_user_id, UserUnit.unit_id == unit.id)
    result = await db.execute(stmt_target)
    target_link = result.scalars().first()
    
    if not target_link:
        raise HTTPException(status_code=404, detail="Member not found")
        
    if target_user_id == current_user.id:
         raise HTTPException(status_code=400, detail="Cannot remove yourself")

    # Check Requester Role
    stmt_requester = select(UserUnit).where(UserUnit.user_id == current_user.id, UserUnit.unit_id == unit.id)
    res_req = await db.execute(stmt_requester)
    requester_link = res_req.scalars().first()
    
    if not requester_link:
        raise HTTPException(status_code=403, detail="Access denied")

    # Resolve Roles (handling legacy rows where role might be None)
    req_role = requester_link.role or (HouseholdRole.ADMIN if requester_link.is_primary else HouseholdRole.OTHER)
    tgt_role = target_link.role or (HouseholdRole.ADMIN if target_link.is_primary else HouseholdRole.OTHER)

    # Deletion Hierarchy Logic
    if req_role == HouseholdRole.ADMIN:
        pass # Admin can delete anyone
    elif req_role == HouseholdRole.SUB_ADMIN:
        # Sub-Admin cannot delete Admin
        if tgt_role == HouseholdRole.ADMIN:
            raise HTTPException(status_code=403, detail="Sub-Admin cannot remove the Admin")
    else:
        # Others cannot delete anyone
        raise HTTPException(status_code=403, detail="Only Admin or Sub-Admin can remove members")

    # Fetch removed member's name before deleting
    target_user_res = await db.execute(select(User).where(User.id == target_user_id))
    target_user = target_user_res.scalars().first()
    target_name = target_user.full_name if target_user else "Member"

    await db.delete(target_link)
    await db.commit()

    # SSE: Notify ALL remaining members of the household unit
    from core.events import event_manager
    from datetime import datetime, timezone

    event_payload = {
        "removed_user_id": target_user_id,
        "full_name": target_name,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Get all remaining members of this unit and notify each one
    remaining_links_res = await db.execute(
        select(UserUnit).where(UserUnit.unit_id == unit.id)
    )
    remaining_links = remaining_links_res.scalars().all()
    for link in remaining_links:
        await event_manager.publish("household:member_removed", event_payload, link.user_id)

    # Notify removed user (Push)
    await notifications.send_removed_from_household(
        db=db,
        user_id=target_user_id,
        unit_number=unit.unit_number,
        house_id=unit.id
    )

    return {"message": "Member removed"}

@router.get("/code", response_model=HouseholdCodeResponse)
async def get_household_code(
    current_user: User = Depends(set_tenant_context),
    unit = Depends(get_current_unit)
):
    if not unit:
         raise HTTPException(status_code=400, detail="Unit context required")
    
    return {"code": unit.access_code or "N/A"}
