from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.models import OTPCode


OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_HOURLY_LIMIT = 5


def get_otp_request_metadata(request: Request) -> dict[str, Optional[str]]:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    request_ip = forwarded_for.split(",", 1)[0].strip()
    if not request_ip:
        request_ip = request.headers.get("x-real-ip")
    if not request_ip and request.client:
        request_ip = request.client.host

    return {
        "request_ip": request_ip,
        "request_user_agent": request.headers.get("user-agent"),
        "request_path": request.url.path,
    }


async def can_issue_otp(
    db: AsyncSession,
    *,
    email: str,
    otp_type: str,
    reveal_limit: bool = True,
) -> bool:
    now = datetime.now(timezone.utc)
    cooldown_since = now - timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS)
    hour_since = now - timedelta(hours=1)

    recent_otp = (
        await db.execute(
            select(OTPCode.id)
            .where(
                OTPCode.email == email,
                OTPCode.type == otp_type,
                OTPCode.created_at >= cooldown_since,
            )
            .limit(1)
        )
    ).scalar()
    if recent_otp:
        if reveal_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait before requesting another OTP",
            )
        return False

    hourly_count = (
        await db.execute(
            select(func.count(OTPCode.id)).where(
                OTPCode.email == email,
                OTPCode.type == otp_type,
                OTPCode.created_at >= hour_since,
            )
        )
    ).scalar_one()
    if hourly_count >= OTP_HOURLY_LIMIT:
        if reveal_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many OTP requests. Please try again later",
            )
        return False

    return True
