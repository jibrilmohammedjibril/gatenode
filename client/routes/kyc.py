from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.db import get_db
from core.deps import get_current_user
from core.models import (
    KYCSession,
    User,
    WalletProfile,
)
from core.wallet_setup import provision_wallet_virtual_account, wallet_virtual_account_payload
from core.rate_limit import RateLimits, limiter
from schemas import (
    KYCActionResponse,
    KYCSubmitRequest,
)

router = APIRouter(prefix="/kyc", tags=["KYC"])
logger = logging.getLogger(__name__)


@router.post("/submit", response_model=KYCActionResponse)
@limiter.limit(RateLimits.SENSITIVE)
async def submit_kyc(
    request: Request,
    data: KYCSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wallet_profile = await provision_wallet_virtual_account(
        db,
        user=current_user,
        bvn=data.bvn,
        phone_number=data.phone_number,
    )

    return {
        "status": "success",
        "message": "Verification and wallet creation completed successfully",
        "data": {"reference": wallet_profile.nomba_account_ref},
        "virtualAccount": wallet_virtual_account_payload(wallet_profile),
        "walletStatus": "active",
    }
