import logging
import json
import hmac
import hashlib
import base64
from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.config import settings
from core.events import event_manager
from core.models import Transaction, User, UserUnit, WalletHistory, WebhookLog, WalletProfile
from core.notifications import notifications
from core.rate_limit import limiter, RateLimits

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = logging.getLogger(__name__)

async def _create_webhook_log(
    db: AsyncSession,
    *,
    provider: str,
    event_type: str,
    payload: dict[str, Any],
    headers: dict[str, Any],
    method: str = "POST",
    url: str | None = None,
) -> WebhookLog:
    log_entry = WebhookLog(
        provider=provider,
        method=method,
        url=url,
        headers=headers,
        event_type=event_type,
        payload=payload,
        status="pending",
    )
    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)
    return log_entry


async def _update_webhook_log(
    db: AsyncSession,
    log_entry: WebhookLog,
    *,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    log_entry.status = status
    if error_message:
        log_entry.error_message = error_message
    
    db.add(log_entry)
    await db.commit()


def _extract_reference(payload: dict[str, Any]) -> Optional[str]:
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    for key in (
        "merchantTxRef",
        "reference",
        "transactionRef",
        "transferReference",
        "providerReference",
        "id",
    ):
        value = data.get(key) or payload.get(key)
        if value:
            return str(value)
    return None


def _extract_amount_kobo(payload: dict[str, Any]) -> int:
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    for key in ("amount", "amountPaid", "paidAmount", "value", "transactionAmount"):
        value = data.get(key) or payload.get(key)
        if value is None:
            continue
        try:
            amount = float(value)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        return int(amount * 100) if "." in str(value) else int(amount)
    return 0


def _normalize_headers(headers: Any) -> dict[str, str]:
    try:
        return {str(key).lower(): str(value) for key, value in headers.items()}
    except Exception:
        return {}


def _signature_materials(body_bytes: bytes, timestamp: str | None) -> list[bytes]:
    body_text = body_bytes.decode("utf-8", errors="ignore")
    timestamp_text = (timestamp or "").strip()
    candidates = [body_bytes, body_text.encode("utf-8")]
    if timestamp_text:
        candidates.extend(
            [
                f"{timestamp_text}.{body_text}".encode("utf-8"),
                f"{timestamp_text}{body_text}".encode("utf-8"),
                f"{body_text}{timestamp_text}".encode("utf-8"),
            ]
        )
    return candidates


def _derive_signatures(secret: str, body_bytes: bytes, timestamp: str | None) -> set[str]:
    signatures: set[str] = set()
    for payload in _signature_materials(body_bytes, timestamp):
        digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
        signatures.add(digest.hex())
        signatures.add(base64.b64encode(digest).decode("utf-8"))
    return signatures


def _verify_nomba_webhook_signature(headers: dict[str, Any], body_bytes: bytes) -> bool:
    secret = settings.NOMBA_WEBHOOK_SECRET
    if not secret:
        return True

    normalized = _normalize_headers(headers)
    signature = (
        normalized.get("nomba-sig-value")
        or normalized.get("nomba-signature")
        or normalized.get("x-nomba-signature")
    )
    if not signature:
        return False

    algorithm = (normalized.get("nomba-signature-algorithm") or "").lower()
    if algorithm and "sha" not in algorithm and "hmac" not in algorithm:
        return False

    timestamp = normalized.get("nomba-timestamp")
    candidates = _derive_signatures(secret, body_bytes, timestamp)
    return signature in candidates


def _extract_transfer_state(payload: dict[str, Any]) -> str:
    event_type = str(payload.get("event") or payload.get("type") or "").lower()
    if "fail" in event_type:
        return "failed"
    if "pending" in event_type or "processing" in event_type:
        return "pending"
    if "success" in event_type or "completed" in event_type:
        return "success"

    data = payload.get("data") or {}
    if isinstance(data, dict):
        for key in ("status", "state", "transferStatus", "transactionStatus"):
            value = data.get(key)
            if value:
                return str(value).lower()
    return "pending"


async def _apply_wallet_funding_webhook(
    db: AsyncSession,
    *,
    payload: dict[str, Any],
    event_type: str,
) -> bool:
    if event_type not in {
        "payment.success",
        "payment_success",
        "transfer.success",
        "transaction.success",
    }:
        return False

    data = payload.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    account_ref = data.get("accountRef") or data.get("accountId") or payload.get("accountRef")
    if not account_ref:
        return False

    amount_kobo = _extract_amount_kobo(payload)
    if amount_kobo <= 0:
        return False

    wallet_profile = (
        await db.execute(select(WalletProfile).where(WalletProfile.nomba_account_ref == account_ref))
    ).scalars().first()
    if not wallet_profile:
        return False

    user = (await db.execute(select(User).where(User.id == wallet_profile.user_id))).scalars().first()
    if not user:
        return False

    reference = _extract_reference(payload) or f"nomba_{wallet_profile.id}_{amount_kobo}"
    txn = (
        await db.execute(
            select(Transaction).where(
                Transaction.reference == reference,
                Transaction.provider == "nomba",
            )
        )
    ).scalars().first()

    metadata: dict[str, Any] = {}
    if txn and txn.metadata_json:
        try:
            parsed = json.loads(txn.metadata_json)
            if isinstance(parsed, dict):
                metadata = parsed
        except Exception:
            metadata = {}

    if metadata.get("wallet_credit_applied"):
        return True
    if txn and (txn.status or "").lower() == "success":
        metadata["wallet_credit_applied"] = True
        txn.metadata_json = json.dumps(metadata)
        db.add(txn)
        await db.commit()
        return True

    if not txn:
        txn = Transaction(
            reference=reference,
            provider="nomba",
            amount=amount_kobo,
            status="pending",
            user_id=user.id,
            description="Wallet Funding",
            transaction_type="Credit",
            metadata_json=json.dumps(
                {
                    "wallet_credit_applied": False,
                    "nomba_event_type": event_type,
                    "account_ref": account_ref,
                }
            ),
        )
        db.add(txn)
        await db.flush()

    user.wallet_balance += amount_kobo
    metadata.update(
        {
            "wallet_credit_applied": True,
            "nomba_event_type": event_type,
            "account_ref": account_ref,
        }
    )
    txn.amount = amount_kobo
    txn.status = "success"
    txn.user_id = user.id
    txn.description = "Wallet Funding"
    txn.transaction_type = "Credit"
    txn.metadata_json = json.dumps(metadata)
    db.add(txn)
    db.add(user)

    unit_link = (
        await db.execute(
            select(UserUnit).where(
                UserUnit.user_id == user.id,
                UserUnit.is_primary == True,
            )
        )
    ).scalars().first()
    if unit_link:
        db.add(
            WalletHistory(
                unit_id=unit_link.unit_id,
                amount=amount_kobo,
                description="Wallet Top Up",
            )
        )

    await db.commit()

    await event_manager.publish(
        "wallet:balance_updated",
        {
            "new_balance": user.wallet_balance / 100.0,
            "change_amount": amount_kobo / 100.0,
            "change_type": "credit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        user.id,
    )
    return True


async def _apply_transfer_out_webhook(
    db: AsyncSession,
    *,
    payload: dict[str, Any],
    event_type: str,
) -> bool:
    reference = _extract_reference(payload)
    if not reference:
        return False

    txn = (
        await db.execute(
            select(Transaction).where(
                Transaction.reference == reference,
                Transaction.provider == "nomba_transfer_out",
            )
        )
    ).scalars().first()
    if not txn:
        return False

    previous_status = (txn.status or "").lower()
    transfer_state = _extract_transfer_state(payload)
    metadata = {}
    if txn.metadata_json:
        try:
            parsed = json.loads(txn.metadata_json)
            if isinstance(parsed, dict):
                metadata = parsed
        except Exception:
            metadata = {}

    balance_applied = bool(metadata.get("balance_applied"))
    user = None
    if txn.user_id:
        user = (await db.execute(select(User).where(User.id == txn.user_id))).scalars().first()

    if transfer_state == "success":
        txn.status = "success"
        if user and not balance_applied:
            user.wallet_balance -= txn.amount
            metadata["balance_applied"] = True
            txn.metadata_json = json.dumps(metadata)
            db.add(user)
            await event_manager.publish(
                "wallet:balance_updated",
                {
                    "new_balance": user.wallet_balance / 100.0,
                    "change_amount": txn.amount / 100.0,
                    "change_type": "debit",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                user.id,
            )
    elif transfer_state == "failed":
        txn.status = "failed"
    elif previous_status == "success":
        return True
    else:
        txn.status = "pending"

    db.add(txn)
    await db.commit()
    return True


@router.post("/nomba")
@limiter.limit(RateLimits.WEBHOOK)
async def nomba_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body_bytes = await request.body()
    headers = dict(request.headers)
    try:
        payload = json.loads(body_bytes)
    except Exception as exc:
        logger.error(f"Failed to parse Nomba webhook: {exc}")
        return {"status": "error", "message": "Invalid JSON"}

    event_type = payload.get("event") or payload.get("type") or "unknown"
    
    log_entry = await _create_webhook_log(
        db,
        provider="nomba",
        event_type=event_type,
        payload=payload,
        headers=headers,
        method=request.method,
        url=str(request.url),
    )

    if not _verify_nomba_webhook_signature(headers, body_bytes):
        await _update_webhook_log(
            db,
            log_entry,
            status="failed",
            error_message="Invalid Nomba webhook signature",
        )
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    logger.info("=== NOMBA WEBHOOK PROCESSING EVENT: %s ===", event_type)
    
    try:
        if event_type in {"transfer.success", "transaction.success", "transfer.failed", "transaction.failed", "transfer.pending", "transaction.pending"}:
            handled = await _apply_transfer_out_webhook(
                db,
                payload=payload,
                event_type=event_type,
            )
            if handled:
                await _update_webhook_log(
                    db,
                    log_entry,
                    status="success",
                )
                return {"status": "success"}

        if await _apply_wallet_funding_webhook(db, payload=payload, event_type=event_type):
            await _update_webhook_log(
                db,
                log_entry,
                status="success",
            )
            return {"status": "success"}

        await _update_webhook_log(
            db,
            log_entry,
            status="ignored",
        )
        return {"status": "success"}
    except Exception as exc:
        logger.error("Nomba Webhook Error: %s", exc, exc_info=True)
        await _update_webhook_log(
            db,
            log_entry,
            status="error",
            error_message=str(exc)
        )
        return {"status": "error", "message": "Internal error processing webhook"}
