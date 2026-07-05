from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.models import User, WalletProfile, split_person_name
from core.nomba import NombaAPIError, nomba_service


def normalize_bvn(bvn: str) -> str:
    digits = "".join(ch for ch in (bvn or "") if ch.isdigit())
    if len(digits) != 11:
        raise HTTPException(status_code=400, detail="bvn must be an 11-digit numeric value")
    return digits


def ensure_wallet_profile(user_id: str, wallet_profile: WalletProfile | None) -> WalletProfile:
    if wallet_profile:
        return wallet_profile

    return WalletProfile(
        user_id=user_id,
        provider="nomba",
        status="pending_kyc",
    )


def resolved_nomba_name_parts(user: User) -> dict[str, str]:
    if user.first_name and user.last_name:
        return {
            "first_name": user.first_name,
            "last_name": user.last_name,
        }

    parsed = split_person_name(user.full_name)
    first_name = parsed["first_name"] or "Resident"
    last_name = parsed["last_name"] or first_name
    return {
        "first_name": first_name,
        "last_name": last_name,
    }


def wallet_virtual_account_payload(wallet_profile: WalletProfile) -> dict[str, object]:
    return {
        "bank_name": wallet_profile.bank_name,
        "account_number": wallet_profile.account_number,
        "account_name": wallet_profile.account_name,
        "assigned": True,
    }


async def provision_wallet_virtual_account(
    db: AsyncSession,
    *,
    user: User,
    bvn: str,
    phone_number: str | None = None,
) -> WalletProfile:
    normalized_bvn = normalize_bvn(bvn)

    if phone_number:
        user.phone_number = phone_number

    wallet_profile = (
        await db.execute(select(WalletProfile).where(WalletProfile.user_id == user.id))
    ).scalars().first()
    wallet_profile = ensure_wallet_profile(user.id, wallet_profile)

    has_full_virtual_account = bool(
        wallet_profile.nomba_account_ref
        and wallet_profile.nomba_account_id
        and wallet_profile.bank_name
        and wallet_profile.account_number
        and wallet_profile.account_name
    )
    if wallet_profile.status == "active" and has_full_virtual_account:
        db.add(user)
        db.add(wallet_profile)
        await db.commit()
        return wallet_profile

    name_parts = resolved_nomba_name_parts(user)
    account_ref = wallet_profile.nomba_account_ref or uuid.uuid4().hex
    account_name = f"{name_parts['first_name']} {name_parts['last_name']}"

    try:
        response = await nomba_service.create_virtual_account(
            account_ref=account_ref,
            account_name=account_name,
            bvn=normalized_bvn,
            currency="NGN",
        )
    except NombaAPIError as exc:
        wallet_profile.status = "account_creation_failed"
        wallet_profile.kyc_message = str(exc)
        db.add(user)
        db.add(wallet_profile)
        await db.commit()
        status_code = 502 if exc.status_code is None or exc.status_code >= 500 else 400
        raise HTTPException(status_code=status_code, detail=str(exc))

    res_data = response.get("data", {})
    account_id = res_data.get("accountId")
    bank_name = res_data.get("bankName")
    account_number = res_data.get("accountNumber")
    account_name_response = res_data.get("accountName")

    if not account_id or not bank_name or not account_number or not account_name_response:
        wallet_profile.status = "account_creation_failed"
        wallet_profile.kyc_message = "Nomba did not return complete virtual account details"
        db.add(user)
        db.add(wallet_profile)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Nomba virtual account creation did not return account details",
        )

    wallet_profile.nomba_account_ref = res_data.get("accountRef") or account_ref
    wallet_profile.nomba_account_id = account_id
    wallet_profile.bank_name = bank_name
    wallet_profile.account_number = account_number
    wallet_profile.account_name = account_name_response
    wallet_profile.status = "active"
    wallet_profile.kyc_message = "Virtual account created successfully"
    user.bvn_verified = True

    db.add(user)
    db.add(wallet_profile)
    await db.commit()
    await db.refresh(wallet_profile)
    return wallet_profile
