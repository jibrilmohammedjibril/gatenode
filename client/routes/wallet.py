import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from core.db import get_db
from core.billing import display_bill_transaction_text
from core.models import User, Transaction, WalletProfile
from core.deps import get_current_user, set_tenant_context
from core.events import event_manager
from core.nomba import nomba_service, NombaAPIError
from core.security import verify_transaction_pin
from core.wallet_setup import provision_wallet_virtual_account, wallet_virtual_account_payload
from schemas import (
    WalletBalanceResponse, Transaction as TransactionSchema, WalletVirtualAccountEnvelope,
    WalletStatusResponse,
    WalletSetupRequest,
    WalletSetupResponse,
    WalletTransferOutRequest,
    WalletTransferOutResponse,
)

router = APIRouter(prefix="/wallet", tags=["Wallet"])


def _map_wallet_status(wallet_profile: WalletProfile | None) -> str:
    if not wallet_profile:
        return "wallet_setup_required"

    internal_status = wallet_profile.status
    if internal_status in {"active"}:
        return "active"
    if internal_status in {"awaiting_document"}:
        return "awaiting_document"
    if internal_status in {"manual_review"}:
        return "manual_review"
    if internal_status in {"reenter_information"}:
        return "reenter_information"
    if internal_status in {"rejected", "verification_failed"}:
        return "rejected"
    if internal_status in {"kyc_approved"}:
        return "account_pending"
    if internal_status in {"account_pending"}:
        return "account_pending"
    if internal_status in {"account_creation_failed"}:
        return "wallet_setup_failed"
    if internal_status in {"pending_kyc"}:
        return "wallet_setup_required"
    return "pending_verification"


def _wallet_status_meta(wallet_profile: WalletProfile | None) -> tuple[str | None, str | None]:
    status = _map_wallet_status(wallet_profile)
    message = getattr(wallet_profile, "kyc_message", None)

    if status == "wallet_setup_required":
        return "start_wallet_setup", message or "Set up your virtual account to fund your wallet."
    if status == "wallet_setup_failed":
        return "retry_wallet_setup", message or "Wallet setup failed. Try again to create your virtual account."
    if status == "pending_verification":
        return "wait", message or "Verification is still in progress."
    if status == "awaiting_document":
        return "upload_document", message or "A document is required to continue KYC."
    if status == "manual_review":
        return "wait", message or "Your document is under manual review."
    if status == "reenter_information":
        return "resubmit_kyc", message or "Some information needs to be corrected and resubmitted."
    if status == "rejected":
        return "contact_support", message or "Wallet verification was rejected."
    if status == "account_pending":
        return "wait", message or "Verification passed. Account number is being assigned."
    if status == "active":
        return None, message or "Wallet is ready."
    return None, message


def _wallet_status_payload(wallet_profile: WalletProfile | None) -> dict:
    status = _map_wallet_status(wallet_profile)
    next_action, message = _wallet_status_meta(wallet_profile)
    has_virtual_account = bool(
        wallet_profile
        and wallet_profile.bank_name
        and wallet_profile.account_number
        and wallet_profile.account_name
    )

    virtual_account = None
    if has_virtual_account:
        virtual_account = {
            "bank_name": wallet_profile.bank_name,
            "account_number": wallet_profile.account_number,
            "account_name": wallet_profile.account_name,
            "assigned": True,
        }

    reason = None
    if status in {"rejected", "reenter_information"}:
        reason = getattr(wallet_profile, "kyc_message", None)

    return {
        "status": status,
        "nextAction": next_action,
        "message": message,
        "reason": reason,
        "requiredDocuments": (wallet_profile.kyc_requirements or []) if wallet_profile else [],
        "virtualAccountAssigned": has_virtual_account,
        "virtualAccount": virtual_account,
    }


def _wallet_setup_response(wallet_profile: WalletProfile) -> dict:
    return {
        "status": "success",
        "message": "Virtual account created successfully",
        "data": {"reference": wallet_profile.nomba_account_ref},
        "virtualAccount": wallet_virtual_account_payload(wallet_profile),
        "walletStatus": _map_wallet_status(wallet_profile),
    }


def _normalized_transfer_reference() -> str:
    return f"WDR-{uuid.uuid4().hex[:12].upper()}"


def _validate_transfer_details(data: WalletTransferOutRequest) -> None:
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")

    account_number = (data.account_number or "").strip()
    account_name = (data.account_name or "").strip()
    bank_code = (data.bank_code or "").strip()
    bank_name = (data.bank_name or "").strip()

    if not account_number.isdigit() or len(account_number) != 10:
        raise HTTPException(status_code=400, detail="accountNumber must be a 10-digit bank account number")
    if not bank_code:
        raise HTTPException(status_code=400, detail="bankCode is required")
    if not bank_name:
        raise HTTPException(status_code=400, detail="bankName is required")
    if not account_name:
        raise HTTPException(status_code=400, detail="accountName is required")


def _extract_transfer_provider_reference(response: object) -> str | None:
    if not isinstance(response, dict):
        return None

    data = response.get("data")
    if not isinstance(data, dict):
        data = {}

    for key in ("id", "reference", "merchantTxRef", "merchantReference", "transferReference"):
        value = data.get(key) or response.get(key)
        if value:
            return str(value)
    return None


def _extract_transfer_state(response: object) -> str | None:
    if not isinstance(response, dict):
        return None

    for source in (response, response.get("data") if isinstance(response.get("data"), dict) else {}):
        for key in ("status", "state", "transferStatus", "transactionStatus"):
            value = source.get(key) if isinstance(source, dict) else None
            if value:
                return str(value).lower()
    return None


@router.get("/balance", response_model=WalletBalanceResponse)
async def get_balance(
    current_user: User = Depends(set_tenant_context),
    db: AsyncSession = Depends(get_db)
):
    wallet_profile = (
        await db.execute(select(WalletProfile).where(WalletProfile.user_id == current_user.id))
    ).scalars().first()
    mapped_status = _map_wallet_status(wallet_profile)

    if not wallet_profile or mapped_status == "wallet_setup_required":
        raise HTTPException(status_code=404, detail="Wallet setup is required before balance can be viewed")
    if mapped_status == "wallet_setup_failed":
        raise HTTPException(status_code=409, detail="Wallet setup failed. Please try again")
    if mapped_status == "pending_verification":
        raise HTTPException(status_code=409, detail="Wallet verification is still in progress")
    if mapped_status == "awaiting_document":
        raise HTTPException(status_code=409, detail="Wallet verification requires a document upload")
    if mapped_status == "manual_review":
        raise HTTPException(status_code=409, detail="Wallet verification is under manual review")
    if mapped_status == "reenter_information":
        raise HTTPException(status_code=409, detail="Wallet verification needs corrected information")
    if mapped_status == "account_pending":
        raise HTTPException(status_code=409, detail="Wallet account number is still being assigned")
    if mapped_status == "rejected":
        raise HTTPException(status_code=403, detail="Wallet verification was rejected")
    if mapped_status != "active":
        raise HTTPException(status_code=409, detail="Wallet is not ready")
    if not wallet_profile.nomba_account_id:
        raise HTTPException(status_code=409, detail="Wallet is active but missing account reference")

    try:
        balance_kobo = await nomba_service.fetch_account_balance_kobo(account_id=wallet_profile.nomba_account_id)
    except NombaAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch wallet balance from Nomba: {exc}")

    return {
        "balance": balance_kobo / 100.0,  # Convert to Naira
        "currency": "NGN"
    }

@router.get("/transactions", response_model=List[TransactionSchema])
async def get_transactions(
    current_user: User = Depends(set_tenant_context),
    db: AsyncSession = Depends(get_db)
):
    # Fetch Wallet History (Actual balance changes)
    # Fetch Transactions (User Based)
    stmt = select(Transaction).where(Transaction.user_id == current_user.id).order_by(Transaction.created_at.desc()).limit(50)
    result = await db.execute(stmt)
    txns = result.scalars().all()
    
    # Map to Schema
    transactions = []
    for t in txns:
        title = display_bill_transaction_text(t.description) if t.description else "Transaction"
        # category logic
        category = "funding" if t.transaction_type == "Credit" else "bills"
        if t.description and "electricity" in t.description.lower(): category = "electricity"
        if t.description and "data" in t.description.lower(): category = "internet"
        if t.description and "airtime" in t.description.lower(): category = "airtime"
        if t.description and "cable" in t.description.lower(): category = "cable"
        if t.description and ("withdraw" in t.description.lower() or "transfer" in t.description.lower()):
            category = "transfer_out"
        
        transactions.append({
            "id": t.reference or t.id,
            "type": t.transaction_type.lower() if t.transaction_type else "credit",
            "category": category,
            "amount": abs(t.amount) / 100.0, # Convert to Naira
            "status": t.status,
            "date": str(t.created_at),
            "title": title,
        })
        
    return transactions


@router.post("/transfer-out", response_model=WalletTransferOutResponse)
async def transfer_out(
    data: WalletTransferOutRequest,
    current_user: User = Depends(set_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    verify_transaction_pin(current_user, data.transaction_pin)
    _validate_transfer_details(data)

    wallet_profile = (
        await db.execute(select(WalletProfile).where(WalletProfile.user_id == current_user.id))
    ).scalars().first()
    mapped_status = _map_wallet_status(wallet_profile)

    if not wallet_profile or mapped_status != "active":
        raise HTTPException(status_code=409, detail="Set up your virtual account before withdrawing")
    if not wallet_profile.nomba_account_id:
        raise HTTPException(status_code=409, detail="Wallet is active but missing account reference")

    amount_kobo = int(round(data.amount * 100))
    if current_user.wallet_balance < amount_kobo:
        raise HTTPException(status_code=400, detail="Insufficient wallet balance")

    reference = _normalized_transfer_reference()
    description = f"Wallet Withdrawal: {data.bank_name} - {data.account_name}"

    txn = Transaction(
        reference=reference,
        provider="nomba_transfer_out",
        amount=amount_kobo,
        status="pending",
        user_id=current_user.id,
        unit_id=None,
        description=description,
        transaction_type="Debit",
        metadata_json=json.dumps(
            {
                "type": "wallet_transfer_out",
                "bank_name": data.bank_name,
                "bank_code": data.bank_code,
                "account_number": data.account_number,
                "account_name": data.account_name,
                "narration": data.narration,
            }
        ),
    )
    db.add(txn)
    await db.commit()

    try:
        response = await nomba_service.create_transfer(
            amount=amount_kobo,
            account_number=data.account_number,
            account_name=data.account_name,
            bank_code=data.bank_code,
            narration=data.narration or "Wallet withdrawal",
            reference=reference,
        )
        provider_reference = _extract_transfer_provider_reference(response)
        transfer_state = _extract_transfer_state(response) or "success"
        is_final_success = transfer_state in {"success", "completed", "approved", "successful"}
        balance_applied = False

        txn.metadata_json = json.dumps(
            {
                "type": "wallet_transfer_out",
                "bank_name": data.bank_name,
                "bank_code": data.bank_code,
                "account_number": data.account_number,
                "account_name": data.account_name,
                "narration": data.narration,
                "provider_reference": provider_reference,
                "transfer_state": transfer_state,
                "balance_applied": is_final_success,
            }
        )

        if is_final_success:
            txn.status = "success"
            current_user.wallet_balance -= amount_kobo
            balance_applied = True
            db.add(current_user)
            await event_manager.publish(
                "wallet:balance_updated",
                {
                    "new_balance": current_user.wallet_balance / 100.0,
                    "change_amount": amount_kobo / 100.0,
                    "change_type": "debit",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                current_user.id,
            )
        else:
            txn.status = "pending"

        db.add(txn)
        await db.commit()

        return {
            "status": txn.status,
            "reference": reference,
            "amount": amount_kobo / 100.0,
            "bankName": data.bank_name,
            "accountNumber": data.account_number,
            "accountName": data.account_name,
            "providerReference": provider_reference,
            "message": "Transfer queued successfully" if not balance_applied else "Transfer completed successfully",
        }
    except NombaAPIError as exc:
        txn.status = "failed"
        txn.metadata_json = json.dumps(
            {
                "type": "wallet_transfer_out",
                "bank_name": data.bank_name,
                "bank_code": data.bank_code,
                "account_number": data.account_number,
                "account_name": data.account_name,
                "narration": data.narration,
                "error": str(exc),
            }
        )
        db.add(txn)
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Nomba transfer failed: {exc}")


@router.post("/setup", response_model=WalletSetupResponse)
async def setup_wallet(
    data: WalletSetupRequest,
    current_user: User = Depends(set_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    wallet_profile = await provision_wallet_virtual_account(
        db,
        user=current_user,
        bvn=data.bvn,
        phone_number=data.phone_number,
    )
    return _wallet_setup_response(wallet_profile)


@router.get("/status", response_model=WalletStatusResponse)
async def get_wallet_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    wallet_profile = (
        await db.execute(select(WalletProfile).where(WalletProfile.user_id == current_user.id))
    ).scalars().first()

    return _wallet_status_payload(wallet_profile)


@router.get("/virtual-account", response_model=WalletVirtualAccountEnvelope)
async def get_virtual_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    wallet_profile = (
        await db.execute(select(WalletProfile).where(WalletProfile.user_id == current_user.id))
    ).scalars().first()

    mapped_status = _map_wallet_status(wallet_profile)

    if not wallet_profile or mapped_status == "wallet_setup_required":
        raise HTTPException(status_code=404, detail="Wallet setup is required before a virtual account can be issued")
    if mapped_status == "wallet_setup_failed":
        raise HTTPException(status_code=409, detail="Wallet setup failed. Please try again")
    if mapped_status == "pending_verification":
        raise HTTPException(status_code=409, detail="Wallet verification is still in progress")
    if mapped_status == "awaiting_document":
        raise HTTPException(status_code=409, detail="Wallet verification requires a document upload")
    if mapped_status == "manual_review":
        raise HTTPException(status_code=409, detail="Wallet verification is under manual review")
    if mapped_status == "reenter_information":
        raise HTTPException(status_code=409, detail="Wallet verification needs corrected information")
    if mapped_status == "account_pending":
        raise HTTPException(status_code=409, detail="Wallet account number is still being assigned")
    if mapped_status == "rejected":
        raise HTTPException(status_code=403, detail="Wallet verification was rejected")
    if mapped_status != "active":
        raise HTTPException(status_code=409, detail="Wallet is not ready")

    if not wallet_profile.bank_name or not wallet_profile.account_number or not wallet_profile.account_name:
        raise HTTPException(status_code=409, detail="Wallet exists but virtual account details are incomplete")

    return {
        "virtualAccount": {
            "bank_name": wallet_profile.bank_name,
            "account_number": wallet_profile.account_number,
            "account_name": wallet_profile.account_name,
            "assigned": True,
        }
    }
