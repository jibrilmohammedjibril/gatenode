import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from core.db import get_db
from core.config import settings
from core.models import User, VisitorInvite, InviteStatus, InviteType
from core.deps import get_current_unit, require_estate_membership
from schemas import InviteCreate, InviteResponse, InviteExtendRequest
from datetime import datetime, timedelta, timezone
from core.whatsapp import send_whatsapp_template
from core.notifications import notifications

router = APIRouter(tags=["Invites"])

def format_invite_status(status: InviteStatus) -> str:
    # Handle both Enum member and raw string (just in case)
    val = status.value if hasattr(status, 'value') else str(status)
    
    if val == InviteStatus.CHECKED_IN.value:
        return "Checked In"
    elif val == InviteStatus.COMPLETED.value:
        return "Completed"
    elif val == InviteStatus.USED.value:
        return "Used"
    else:
        # Fallback: "ACTIVE" -> "Active", "REVOKED" -> "Revoked"
        return val.replace("_", " ").title()

async def process_invite_background(
    invite_id: str,
    visitor_phone: str,
    visitor_name: str,
    host_name: str,
    estate_name: str,
    access_code: str,
    invite_type: str,
    start: datetime,
    end: datetime,
):
    """Heavy background processing for Playwright Graphics, S3, and WhatsApp"""
    from core.whatsapp import send_whatsapp_template
    from fastapi.concurrency import run_in_threadpool
    
    # 1. Format Dates
    date_str = start.strftime("%b %d, %Y")
    start_time_str = start.strftime("%I:%M %p")
    end_time_str = end.strftime("%I:%M %p")
    time_range = f"{start_time_str} - {end_time_str}"
    
    verify_url = f"{settings.PUBLIC_WEB_APP_URL.rstrip('/')}/verify/{access_code}"
    qr_link = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={verify_url}"
    header_link = qr_link
    filename = None
    
    # 2. Async Playwright Image Gen
    try:
        from core.image_gen import generate_invite_image, upload_to_minio, delete_from_minio
        
        invite_type_display = "Group Access" if invite_type.upper() == "GROUP" else "Single Entry"
        img_bytes = await generate_invite_image(
            visitor_name, 
            invite_type_display,
            access_code, 
            date_str, 
            time_range
        )
        
        if img_bytes:
            filename = f"invite_{invite_id}_{int(datetime.now(timezone.utc).timestamp())}.png"
            uploaded_url = await run_in_threadpool(upload_to_minio, img_bytes, filename)
            if uploaded_url:
                header_link = uploaded_url
    except Exception as e:
        print(f"ERROR: Image Generation or Import Failed in background: {e}")
        
    # 3. WhatsApp Components
    maps_query = estate_name.replace(" ", "+") + "+Nigeria" 
    components = [
        {"type": "header", "parameters": [{"type": "image", "image": { "link": header_link }}]},
        {"type": "body", "parameters": [
            { "type": "text", "text": visitor_name },
            { "type": "text", "text": host_name },
            { "type": "text", "text": estate_name },
            { "type": "text", "text": date_str },
            { "type": "text", "text": start_time_str },
            { "type": "text", "text": end_time_str }
        ]},
        {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": maps_query}]}
    ]
    
    # 4. Dispatch WhatsApp
    try:
        await send_whatsapp_template(visitor_phone, "visitor_access_notification_v1", "en", components)
    except Exception as e:
        print(f"ERROR: Failed to dispatch WhatsApp: {e}")
    
    # 5. MinIO Cleanup! (Garbage Collection)
    try:
        if filename and header_link != qr_link:
            from core.image_gen import delete_from_minio
            # Wait 2 minutes for WhatsApp servers to asynchronously download the image
            import asyncio
            await asyncio.sleep(120)
            await run_in_threadpool(delete_from_minio, filename)
    except Exception as e:
        print(f"ERROR: MinIO Garbage Collection failed: {e}")

@router.post("", response_model=InviteResponse, name="create_invite")
async def create_invite(
    data: InviteCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_estate_membership),
    unit = Depends(get_current_unit), # Specific unit context preferred
    db: AsyncSession = Depends(get_db)
):
    print(f"DEBUG: create_invite data: {data}")
    if not unit:
        # Fallback to user's first unit if not specified in header? 
        # Ideally Deps handles this.
         pass
 
    # Logic for validity
    start = datetime.now(timezone.utc)
    if data.valid_from:
        start = datetime.fromisoformat(data.valid_from.replace("Z", "+00:00"))
    
    if data.valid_until:
        end = datetime.fromisoformat(data.valid_until.replace("Z", "+00:00"))
    else:
        hours = data.valid_hours if data.valid_hours else 24
        end = start + timedelta(hours=hours)
    
    # Enum Type - now expecting uppercase from frontend
    try:
        itype = InviteType(data.invite_type.upper())
    except ValueError:
        # Fallback to Single if unknown
        itype = InviteType.SINGLE
    
    visitor_name = data.visitor_name
    print(f"DEBUG: Processing invite for {visitor_name}")
    
    new_invite = VisitorInvite(
        visitor_name=visitor_name,
        visitor_phone=data.visitor_phone,
        valid_from=start,
        valid_until=end,
        user_id=current_user.id,
        estate_id=current_user.estate_id,
        invite_type=itype,
        unit_id=unit.id if unit else None,
        status=InviteStatus.ACTIVE,
        gender=data.visitor_gender,
        expected_guests=data.expected_guests
    )
    
    # Explicitly handle location
    if data.location:
        print(f"DEBUG: Setting location data: {data.location}")
        new_invite.location_latitude = data.location.latitude
        new_invite.location_longitude = data.location.longitude
        new_invite.location_accuracy = data.location.accuracy
    else:
        print("DEBUG: No location data provided.")
    
    db.add(new_invite)
    await db.commit()
    await db.refresh(new_invite)
    
    print(f"DEBUG: Invite created with Phone: {new_invite.visitor_phone}, Lat: {new_invite.location_latitude}")
    
    if new_invite.visitor_phone:
        # Get Estate Name synchronously before branching off DB session
        estate_name = "Resident Estate"
        try:
            from core.models import Estate
            est_stmt = select(Estate).where(Estate.id == current_user.estate_id)
            est_res = await db.execute(est_stmt)
            est = est_res.scalars().first()
            if est:
                estate_name = est.name
        except Exception as e:
            print(f"ERROR: Failed to fetch estate name: {e}")

        # Queue Heavy Whatsapp/Playwright logic to background!
        background_tasks.add_task(
            process_invite_background,
            invite_id=new_invite.id,
            visitor_phone=new_invite.visitor_phone,
            visitor_name=new_invite.visitor_name,
            host_name=current_user.full_name,
            estate_name=estate_name,
            access_code=new_invite.access_code,
            invite_type=new_invite.invite_type.value,
            start=start,
            end=end
        )
    
    return {
        "id": new_invite.id,
        "access_code": new_invite.access_code,
        "visitor_name": new_invite.visitor_name,
        "valid_from": new_invite.valid_from.isoformat().replace("+00:00", "Z"),
        "valid_until": new_invite.valid_until.isoformat().replace("+00:00", "Z"),
        "status": format_invite_status(new_invite.status),
        "inviteType": new_invite.invite_type,
        "qr_code_data": f"{settings.PUBLIC_WEB_APP_URL.rstrip('/')}/verify/{new_invite.access_code}"
    }

@router.get("", response_model=list[InviteResponse])
async def list_invites(
    current_user: User = Depends(require_estate_membership),
    unit = Depends(get_current_unit),
    db: AsyncSession = Depends(get_db)
):
    # Active or Checked-In invites
    # Active (future) OR Checked-In (any time)
    now_utc = datetime.now(timezone.utc)
    from sqlalchemy import or_
    
    query = select(VisitorInvite).where(
        VisitorInvite.user_id == current_user.id,
        or_(
            # Case 1: Active and valid
            (VisitorInvite.status == InviteStatus.ACTIVE) & (VisitorInvite.valid_until > now_utc),
            # Case 2: Checked In (regardless of time)
            VisitorInvite.status == InviteStatus.CHECKED_IN
        )
    ).order_by(VisitorInvite.valid_until.asc())
    
    if unit:
        query = query.where(VisitorInvite.unit_id == unit.id)
        
    result = await db.execute(query)
    invites = result.scalars().all()
    
    # Lazy Expiration Check
    now_utc = datetime.now(timezone.utc)
    expiration_occured = False
    
    for i in invites:
        # Ensure timezone awareness
        if i.valid_until.tzinfo is None:
             i.valid_until = i.valid_until.replace(tzinfo=timezone.utc)
             
        if i.status == InviteStatus.ACTIVE and i.valid_until < now_utc:
            i.status = InviteStatus.EXPIRED
            expiration_occured = True
            
    if expiration_occured:
        await db.commit()
    
    return [
        {
            "id": i.id,
            "access_code": i.access_code,
            "visitor_name": i.visitor_name,
            "valid_from": i.valid_from.isoformat().replace("+00:00", "Z"),
            "valid_until": i.valid_until.isoformat().replace("+00:00", "Z"),
            "status": format_invite_status(i.status),
            "inviteType": i.invite_type,
            "qr_code_data": f"{settings.PUBLIC_WEB_APP_URL.rstrip('/')}/verify/{i.access_code}"
        }
        for i in invites
    ]

@router.get("/history", response_model=list[InviteResponse])
async def history_invites(
    page: int = 1,
    limit: int = 20,
    status: Optional[str] = Query(None),
    current_user: User = Depends(require_estate_membership),
    unit = Depends(get_current_unit),
    db: AsyncSession = Depends(get_db)
):
    query = select(VisitorInvite).where(VisitorInvite.user_id == current_user.id)
    
    if unit:
        query = query.where(VisitorInvite.unit_id == unit.id)

    if status:
        # Map frontend status to DB enum
        status_lower = status.lower()
        if status_lower == "pending":
            query = query.where(VisitorInvite.status == InviteStatus.ACTIVE)
        elif status_lower == "arrived":
            # Include all past/present arrival states
            query = query.where(VisitorInvite.status.in_([InviteStatus.USED, InviteStatus.CHECKED_IN, InviteStatus.COMPLETED]))
        elif status_lower == "active":
             query = query.where(VisitorInvite.status == InviteStatus.ACTIVE)
        elif status_lower == "expired":
             query = query.where(VisitorInvite.status == InviteStatus.EXPIRED)
        elif status_lower == "revoked":
             query = query.where(VisitorInvite.status == InviteStatus.REVOKED)
        else:
             # Try direct match (case sensitive or upper)
             try:
                 # Check if valid enum member
                 match = InviteStatus(status.upper())
                 query = query.where(VisitorInvite.status == match)
             except ValueError:
                 pass
        
    # Pagination
    offset = (page - 1) * limit
    query = query.order_by(VisitorInvite.valid_from.desc()).offset(offset).limit(limit)
        
    result = await db.execute(query)
    invites = result.scalars().all()
    
    # Lazy Expiration Check
    now_utc = datetime.now(timezone.utc)
    expiration_occured = False
    
    for i in invites:
        # Ensure timezone awareness
        if i.valid_until.tzinfo is None:
             i.valid_until = i.valid_until.replace(tzinfo=timezone.utc)
             
        if i.status == InviteStatus.ACTIVE and i.valid_until < now_utc:
            i.status = InviteStatus.EXPIRED
            expiration_occured = True
            
    if expiration_occured:
        await db.commit()
    
    return [
        {
            "id": i.id,
            "access_code": i.access_code,
            "visitor_name": i.visitor_name,
            "valid_from": i.valid_from.isoformat().replace("+00:00", "Z"),
            "valid_until": i.valid_until.isoformat().replace("+00:00", "Z"),
            "status": format_invite_status(i.status),
            "inviteType": i.invite_type
        }
        for i in invites
    ]
    
def models_py_valid_until_str(dt):
    return str(dt)

@router.post("/{invite_id}/revoke")
async def revoke_invite(
    invite_id: str,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(VisitorInvite).where(VisitorInvite.id == invite_id, VisitorInvite.user_id == current_user.id)
    result = await db.execute(stmt)
    invite = result.scalars().first()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
        
    invite.status = InviteStatus.REVOKED
    await db.commit()
    
    return {"message": "Invite revoked"}

@router.delete("/{invite_id}")
async def delete_invite(
    invite_id: str,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    """
    Revoke/Delete an invite.
    """
    stmt = select(VisitorInvite).where(VisitorInvite.id == invite_id, VisitorInvite.user_id == current_user.id)
    result = await db.execute(stmt)
    invite = result.scalars().first()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
        
    invite.status = InviteStatus.REVOKED
    await db.commit()
    
    return {"message": "Invite revoked"}

@router.post("/{invite_id}/extend")
async def extend_invite(
    invite_id: str,
    data: InviteExtendRequest,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db)
):
    """Extend invite validity."""
    stmt = select(VisitorInvite).where(VisitorInvite.id == invite_id, VisitorInvite.user_id == current_user.id)
    result = await db.execute(stmt)
    invite = result.scalars().first()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
        
    from datetime import timezone
    now_utc = datetime.now(timezone.utc)

    if data.valid_until:
        try:
            # Client sends ISO with Z usually. Ensure it is parsed as UTC aware.
            new_expiry = datetime.fromisoformat(data.valid_until.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format")

        # Ensure new_expiry is aware (it should be due to +00:00, but if not force it)
        if new_expiry.tzinfo is None:
            new_expiry = new_expiry.replace(tzinfo=timezone.utc)
    elif data.valid_hours:
        current_expiry = invite.valid_until
        if current_expiry.tzinfo is None:
            current_expiry = current_expiry.replace(tzinfo=timezone.utc)

        # If the invite has already lapsed, extend from now instead of from a past timestamp.
        extension_base = current_expiry if current_expiry > now_utc else now_utc
        new_expiry = extension_base + timedelta(hours=data.valid_hours)
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide validUntil/valid_until or validHours/valid_hours"
        )

    if new_expiry <= now_utc:
         raise HTTPException(status_code=400, detail="New expiry must be in the future")
         
    invite.valid_until = new_expiry
    if invite.status == InviteStatus.EXPIRED:
        invite.status = InviteStatus.ACTIVE
        
    await db.commit()
    await db.refresh(invite)

    valid_until = invite.valid_until
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)

    return {
        "message": "Invite extended",
        "validUntil": valid_until.isoformat().replace("+00:00", "Z"),
    }

@router.post("/verify/{access_code}")
async def verify_invite_access(
    access_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Mock Gate Verification Endpoint.
    """
    stmt = select(VisitorInvite).where(VisitorInvite.access_code == access_code)
    result = await db.execute(stmt)
    invite = result.scalars().first()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invalid Access Code")
        
    if invite.status != InviteStatus.ACTIVE:
        raise HTTPException(status_code=400, detail=f"Invite is {invite.status}")
        
    # Logic for validity
    from datetime import timezone
    now = datetime.now(timezone.utc)
    
    if invite.valid_until.tzinfo is None:
         invite.valid_until = invite.valid_until.replace(tzinfo=timezone.utc)

    if invite.valid_until < now:
        invite.status = InviteStatus.EXPIRED
        await db.commit()
        # Push: Access Denied (Expired)
        await notifications.send_access_denied(db, invite.user_id, invite.visitor_name, invite.id)
        raise HTTPException(status_code=400, detail="Invite Expired")
        
    # Valid!
    if invite.invite_type == InviteType.SINGLE:
        invite.status = InviteStatus.USED
        
    await db.commit()
    
    # Send SMS/WhatsApp to Visitor with Location (if available)
    if invite.visitor_phone and invite.location_latitude is not None and invite.location_longitude is not None:
        # User requested WhatsApp template "hello_world" for address stuff.
        # Since hello_world doesn't take parameters, we can only send the template itself to verify integration.
        # Ideally, we should use a template that accepts parameters or send a location message.
        # For now, following the user's explicit cURL example request:
        
        # 1. Send Template
        await send_whatsapp_template(invite.visitor_phone, "hello_world")
        
        # 2. Log what we WOULD send if we had a proper template
        maps_link = f"https://maps.google.com/?q={invite.location_latitude},{invite.location_longitude}"
        print(f"DEBUG: Sent WhatsApp 'hello_world' to {invite.visitor_phone}. Intended content: {maps_link}")
    
    # SSE: Notify Resident
    from core.events import event_manager
    await event_manager.publish("visitor:invite_used", {
        "invite_id": invite.id,
        "visitor_name": invite.visitor_name,
        "access_code": invite.access_code,
        "status": "arrived",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }, invite.user_id) 
    
    # Push Notification
    await notifications.send_visitor_arrival(db, invite.user_id, invite.visitor_name, invite.id)
    
    return {"valid": True, "visitor": invite.visitor_name}
