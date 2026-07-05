from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta
from sqlalchemy.orm import selectinload
import logging

from core.db import get_db
from schemas import (
    UserProfileResponse, UserProfileUpdate, UnitSimpleResponse, DeviceTokenCreate, 
    PinVerifyRequest, PinChangeRequest, DigitalIDResponse
)
from core.models import User, UserUnit, Unit, Estate, Block, build_full_name, generate_digital_id_token, split_person_name
import boto3
import uuid
from urllib.parse import urlparse
from core.config import settings
import secrets
import string
from core.security import get_password_hash, verify_password
from core.mail import send_email_async
from core.deps import get_current_user

from botocore.client import Config

logger = logging.getLogger(__name__)

def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=f"http{'s' if settings.MINIO_SECURE else ''}://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4', s3={'addressing_style': 'path'})
    )

router = APIRouter(prefix="/user", tags=["User"])


def _resolved_user_names(user: User) -> dict[str, str | None]:
    if user.first_name or user.middle_name or user.last_name:
        return {
            "first_name": user.first_name,
            "middle_name": user.middle_name,
            "last_name": user.last_name,
        }
    return split_person_name(user.full_name)

@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # App is 100% free — always report active subscription with infinite days.
    status = "active"
    days_left = 360
            
    # Fetch primary unit
    stmt = select(UserUnit).where(UserUnit.user_id == current_user.id, UserUnit.is_primary == True)
    result = await db.execute(stmt)
    uu = result.scalars().first()
    unit_id = uu.unit_id if uu else None
    name_parts = _resolved_user_names(current_user)

    return {
        "id": current_user.id,
        "estate_id": current_user.estate_id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "first_name": name_parts["first_name"],
        "middle_name": name_parts["middle_name"],
        "last_name": name_parts["last_name"],
        "phone_number": current_user.phone_number or "",
        "profile_image_url": current_user.profile_image_url, 
        "role": current_user.role,
        "is_active": current_user.is_active,
        "unit_id": unit_id,
        "is_household_admin": bool(uu), # True if primary unit link exists
        "subscription_status": status,
        "subscription_days_remaining": days_left,
        "settings_location_enabled": current_user.settings_location_enabled,
        "settings_push_enabled": current_user.settings_push_enabled,
        "transaction_pin_set": bool(current_user.transaction_pin_hash),
        "date_of_birth": current_user.date_of_birth,
        "gender": current_user.gender,
    }

@router.get("/", response_model=UserProfileResponse)
async def get_user_root(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await get_profile(current_user, db)

@router.patch("/profile", response_model=UserProfileResponse)
async def update_profile(
    request: Request,
    first_name: str = Form(None),
    middle_name: str = Form(None),
    last_name: str = Form(None),
    phone_number: str = Form(None),
    date_of_birth: str = Form(None),
    gender: str = Form(None),
    settings_location_enabled: bool = Form(None),
    settings_push_enabled: bool = Form(None),
    file: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update Profile (Multipart/Form-Data).
    All fields are optional.
    """
    raw_form = await request.form()
    logged_form = {}
    for key, value in raw_form.multi_items():
        if hasattr(value, "filename"):
            logged_form[key] = {
                "filename": value.filename,
                "content_type": value.content_type,
            }
        else:
            logged_form[key] = value

    logger.info(
        "PATCH /user/profile received payload for user_id=%s: parsed_fields=%s raw_form=%s",
        current_user.id,
        {
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,
            "phone_number": phone_number,
            "date_of_birth": date_of_birth,
            "gender": gender,
            "settings_location_enabled": settings_location_enabled,
            "settings_push_enabled": settings_push_enabled,
            "file": {
                "filename": file.filename,
                "content_type": file.content_type,
            } if file else None,
        },
        logged_form,
    )

    name_parts = _resolved_user_names(current_user)
    if first_name is not None:
        name_parts["first_name"] = first_name.strip() or None
    if middle_name is not None:
        name_parts["middle_name"] = middle_name.strip() or None
    if last_name is not None:
        name_parts["last_name"] = last_name.strip() or None

    if any(value is not None for value in (first_name, middle_name, last_name)):
        if not name_parts["first_name"] or not name_parts["last_name"]:
            raise HTTPException(status_code=400, detail="first_name and last_name are required when updating names")
        current_user.first_name = name_parts["first_name"]
        current_user.middle_name = name_parts["middle_name"]
        current_user.last_name = name_parts["last_name"]
        current_user.full_name = build_full_name(
            current_user.first_name,
            current_user.middle_name,
            current_user.last_name,
        )
    if phone_number:
        current_user.phone_number = phone_number
    if date_of_birth:
        try:
            current_user.date_of_birth = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="date_of_birth must use YYYY-MM-DD format")
    if gender:
        normalized_gender = gender.strip().upper()
        if normalized_gender not in {"MALE", "FEMALE"}:
            raise HTTPException(status_code=400, detail="gender must be MALE or FEMALE")
        current_user.gender = normalized_gender
    if settings_location_enabled is not None:
        current_user.settings_location_enabled = settings_location_enabled
    if settings_push_enabled is not None:
        current_user.settings_push_enabled = settings_push_enabled

    # Handle Image Upload if provided
    if file:
        if not file.content_type.startswith("image/"):
             raise HTTPException(status_code=400, detail="Invalid file type. Please upload an image.")
             
        ext = file.filename.split(".")[-1]
        filename = f"profiles/{current_user.id}_{uuid.uuid4().hex[:8]}.{ext}"
        
        s3 = get_s3_client()
        
        # 0. Delete Old Image if exists
        if current_user.profile_image_url:
            try:
                # Extract Key from URL
                # URL: http(s)://endpoint/bucket/key
                parsed = urlparse(current_user.profile_image_url)
                path = parsed.path.lstrip("/") # e.g. "bucket/profiles/xyz.jpg" or "profiles/xyz.jpg" (depends on MinIO config)
                
                # If path starts with bucket name, strip it
                if path.startswith(f"{settings.MINIO_BUCKET}/"):
                    key = path.replace(f"{settings.MINIO_BUCKET}/", "", 1)
                else:
                    key = path
                    
                print(f"Deleting Old Profile Image: {key}")
                s3.delete_object(Bucket=settings.MINIO_BUCKET, Key=key)
            except Exception as e:
                print(f"Failed to delete old profile image: {e}")
                # Don't block new upload
        
        try:
            s3.upload_fileobj(
                file.file,
                settings.MINIO_BUCKET,
                filename,
                ExtraArgs={'ContentType': file.content_type}
            )
            # Generate URL
            protocol = "https" if settings.MINIO_SECURE else "http"
            url = f"{protocol}://{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/{filename}"
            
            current_user.profile_image_url = url
            
        except Exception as e:
            print(f"S3 Profile Upload Error: {e}")
            raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    
    return await get_profile(current_user, db)

@router.get("/units", response_model=list[UnitSimpleResponse])
async def list_units(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(UserUnit)
        .where(UserUnit.user_id == current_user.id)
        .options(
            selectinload(UserUnit.unit).selectinload(Unit.block).selectinload(Block.estate)
        )
    )
    result = await db.execute(stmt)
    user_units = result.scalars().all()
    
    resp = []
    for uu in user_units:
        unit = uu.unit
        block = unit.block
        estate = block.estate
        
        resp.append({
            "id": unit.id,
            "unit_number": unit.unit_number,
            "block_name": block.name,
            "estate_name": estate.name, # Assuming estate is loaded
            "role": "Owner" if uu.is_primary else "Resident"
        })
    return resp



@router.delete("/account")
async def request_account_deletion(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Request account deletion (Soft Delete).
    Account will be permanently deleted after 30 days.
    Logging in within this period cancels the deletion.
    """
    current_user.deletion_requested_at = datetime.utcnow()
    db.add(current_user)
    await db.commit()
    
    return {
        "message": "Account scheduled for deletion in 30 days. Log in anytime to cancel.",
        "scheduled_deletion_date": current_user.deletion_requested_at + timedelta(days=30)
    }

# --- Transactional PIN Endpoints ---

@router.post("/pin/verify")
async def verify_pin(data: PinVerifyRequest, current_user: User = Depends(get_current_user)):
    """
    Verify if the provided 4-digit PIN matches the stored hash.
    """
    if not current_user.transaction_pin_hash:
        raise HTTPException(status_code=400, detail="Transaction PIN not set. Please set it first.")
        
    if not verify_password(data.pin, current_user.transaction_pin_hash):
        return {"success": False, "message": "Incorrect PIN"}
        
    return {"success": True, "message": "PIN verified successfully"}

@router.post("/pin/change")
async def change_pin(
    data: PinChangeRequest, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Change Transactional PIN.
    - Requires 'old_pin' if a PIN is already set.
    - Sets new PIN hash.
    """
    # 1. Require Old PIN if set
    if current_user.transaction_pin_hash:
        if not data.old_pin:
             raise HTTPException(status_code=400, detail="Old PIN required to change PIN.")
        if not verify_password(data.old_pin, current_user.transaction_pin_hash):
             raise HTTPException(status_code=400, detail="Current PIN is incorrect.")
    
    # 2. Set New PIN
    current_user.transaction_pin_hash = get_password_hash(data.new_pin)
    db.add(current_user)
    await db.commit()
    
    return {"success": True, "message": "Transaction PIN updated successfully."}

@router.post("/pin/forgot")
async def forgot_pin(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Reset Transactional PIN.
    - Generates a random 4-digit PIN.
    - Hashes and saves it.
    - Sends the PLAIN PIN to user's email.
    """
    # 1. Generate Random PIN
    random_pin = ''.join(secrets.choice(string.digits) for _ in range(4))
    
    # 2. Update DB
    current_user.transaction_pin_hash = get_password_hash(random_pin)
    db.add(current_user)
    await db.commit()
    
    # 3. Send Email
    try:
        await send_email_async(
            email_to=current_user.email,
            subject="Transaction PIN Reset",
            title="Your New Transaction PIN",
            body_text=(
                "You requested a PIN reset. Your new Temporary Transaction PIN is below. "
                "Please use this PIN to authorize transactions, or change it immediately in Settings."
            ),
            access_code=random_pin,
            code_label="TEMPORARY PIN" # Friendly label
        )
    except Exception as e:
        print(f"Failed to send PIN reset email: {e}")
        # We proceed, user might check spam or retry. Ideally we retry.
        
    return {
        "success": True, 
        "message": "A new PIN has been sent to your email. Please change it immediately."
    }

@router.get("/pin/status")
async def get_pin_status(current_user: User = Depends(get_current_user)):
    """
    Check if the user has set a Transaction PIN.
    """
    return {"is_set": bool(current_user.transaction_pin_hash)}

@router.get("/digital-id", response_model=DigitalIDResponse)
async def get_digital_id(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the resident's opaque Digital ID token.
    This token is used to generate the QR code displayed in the app.
    """
    # If token is missing OR it's an old long token (not length 6), regenerate it.
    if not current_user.digital_id_token or len(str(current_user.digital_id_token)) != 6:
        current_user.digital_id_token = generate_digital_id_token()
        current_user.digital_id_refreshed_at = datetime.utcnow()
        db.add(current_user)
        await db.commit()
        await db.refresh(current_user)

    return {
        "token": current_user.digital_id_token,
        "refreshedAt": current_user.digital_id_refreshed_at
    }

@router.post("/digital-id/refresh", response_model=DigitalIDResponse)
async def refresh_digital_id(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Regenerate the resident's Digital ID token.
    Invalidates any previously generated QR codes.
    """
    current_user.digital_id_token = generate_digital_id_token()
    current_user.digital_id_refreshed_at = datetime.utcnow()
    
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    
    return {
        "token": current_user.digital_id_token,
        "refreshedAt": current_user.digital_id_refreshed_at
    }
