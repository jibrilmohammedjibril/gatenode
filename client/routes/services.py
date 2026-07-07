import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.db import get_db
from core.models import User, WalletProfile
from core.deps import get_current_user, get_optional_unit, set_tenant_context
from core.security import verify_transaction_pin
from schemas import (
    ServicePayRequest,
    PhoneValidationRequest, PhoneValidationResponse, ServiceProvider,
    ServiceVerifyRequest, ServiceVerifyResponse
)
from core.utils import get_network_from_phone, normalize_phone_number

from core.services.payment_service import process_external_utility_payment
from core.utility_payments import resolve_service_amount_kobo, select_service_product
from core.nomba import nomba_service, NombaAPIError
from core.config import settings

router = APIRouter(prefix="/services", tags=["Services"])
logger = logging.getLogger(__name__)

_TELCO_NAMES = {
    "mtn": "MTN",
    "glo": "GLO",
    "airtel": "Airtel",
    "9mobile": "9mobile",
}

_CABLE_TYPES = {
    "dstv": "DSTV",
    "gotv": "GOTV",
    "startimes": "Startimes",
    "showmax": "Showmax",
}

_ELECTRICITY_METER_TYPES = [
    {"id": "prepaid", "name": "Prepaid"},
    {"id": "postpaid", "name": "Postpaid"},
]


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
    if internal_status in {"kyc_approved", "account_pending"}:
        return "account_pending"
    if internal_status in {"account_creation_failed"}:
        return "wallet_setup_failed"
    if internal_status in {"pending_kyc"}:
        return "wallet_setup_required"
    return "pending_verification"


def _nomba_category(category: str) -> str:
    # Maps our slugs to the `category` field values Nomba actually returns
    # on each biller object.
    mapping = {
        "electricity": "electricity",
        "cable": "television",
        "data": "data",
        "airtime": "airtime",
        "internet": "data",
    }
    return mapping.get(category.lower(), "")


def _normalize_service_key(value: str) -> str:
    return value.strip().lower()


async def _get_electricity_discos() -> List[Dict[str, Any]]:
    payload = await nomba_service.list_electricity_discos()
    data = payload.get("data", [])
    discos: List[Dict[str, Any]] = []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            disco_id = str(item.get("id") or item.get("disco") or item.get("code") or "").strip()
            disco_name = str(item.get("name") or item.get("discoName") or disco_id).strip()
            if disco_id:
                discos.append({"id": disco_id, "name": disco_name})
    elif isinstance(data, dict):
        for key in ("discos", "items", "results", "data"):
            nested = data.get(key)
            if not isinstance(nested, list):
                continue
            for item in nested:
                if not isinstance(item, dict):
                    continue
                disco_id = str(item.get("id") or item.get("disco") or item.get("code") or "").strip()
                disco_name = str(item.get("name") or item.get("discoName") or disco_id).strip()
                if disco_id:
                    discos.append({"id": disco_id, "name": disco_name})
            if discos:
                break
    return discos


async def _resolve_service_kind(service_id: str) -> str:
    service_key = _normalize_service_key(service_id)
    if service_key in _CABLE_TYPES:
        return "cable"
    if service_key in _TELCO_NAMES:
        return "telco"
    discos = await _get_electricity_discos()
    disco_ids = {str(item["id"]).strip().lower() for item in discos}
    if service_key in disco_ids:
        return "electricity"
    return "unknown"


def _safe_provider_name(value: str) -> str:
    return value if value else "Service"


@router.get("/categories")
async def get_service_categories():
    """
    Return list of supported service categories.
    """
    return [
        {"slug": "electricity", "name": "Electricity", "icon": "zap"},
        {"slug": "data", "name": "Data Bundle", "icon": "wifi"},
        {"slug": "airtime", "name": "Airtime", "icon": "smartphone"},
        {"slug": "cable", "name": "Cable TV", "icon": "tv"},
        {"slug": "internet", "name": "Internet Service", "icon": "globe"},
    ]

@router.get("/billers", response_model=List[ServiceProvider])
async def list_services(
    category: str = Query(..., description="Category slug: electricity, data, airtime, cable, internet"), 
    current_user: User = Depends(get_current_user)
):
    """
    Get Billers for a specific category.
    """
    category_slug = category.lower().strip()
    if category_slug not in {"electricity", "data", "airtime", "cable", "internet"}:
        return []

    logo_map = {
        "MTN": "https://logo.clearbit.com/mtn.com",
        "GLO": "https://logo.clearbit.com/gloworld.com",
        "AIRTEL": "https://logo.clearbit.com/airtel.com",
        "9MOBILE": "https://logo.clearbit.com/9mobile.com.ng",
        "DSTV": "https://logo.clearbit.com/dstv.com",
        "GOTV": "https://logo.clearbit.com/gotvafrica.com",
        "STARTIMES": "https://logo.clearbit.com/startimestv.com",
        "IKEJA": "https://logo.clearbit.com/ikedc.com",
        "EKO": "https://logo.clearbit.com/ekedp.com",
        "ABUJA": "https://logo.clearbit.com/abujaelectricity.com",
        "KANO": "https://logo.clearbit.com/kedco.ng",
        "PORT": "https://www.phied.com.ng/assets/images/logo.png",
        "JOS": "https://logo.clearbit.com/josdisco.com",
        "KADUNA": "https://logo.clearbit.com/kedc.com.ng",
        "ENUGU": "https://logo.clearbit.com/enugudisco.com",
        "IBADAN": "https://logo.clearbit.com/ibedc.com",
        "BENIN": "https://logo.clearbit.com/bedcpower.com",
        "SPECTRANET": "https://logo.clearbit.com/spectranet.com",
        "SMILE": "https://logo.clearbit.com/smile.com.ng",
        "SWIFT": "https://logo.clearbit.com/swiftng.com",
        "IPNX": "https://logo.clearbit.com/ipnxnigeria.net",
        "COBRANET": "https://logo.clearbit.com/cobranet.org",
        "TIZETI": "https://logo.clearbit.com/wifi.com.ng",
        "FIBERON": "https://logo.clearbit.com/fiberone.com.ng",
        "YOLA": "https://logo.clearbit.com/yedc.ng"
    }

    def _logo_for(name: str) -> str:
        name_upper = name.upper()
        for key, url in logo_map.items():
            if key in name_upper:
                return url
        return f"https://ui-avatars.com/api/?name={name}&background=random&size=128"

    if category_slug == "electricity":
        try:
            billers = await _get_electricity_discos()
        except NombaAPIError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch billers: {exc}")

        return [
            {
                "id": b["id"],
                "name": b["name"],
                "type": "electricity",
                "logoUrl": _logo_for(b["name"]),
                "options": [
                    {"id": "prepaid", "name": "Prepaid"},
                    {"id": "postpaid", "name": "Postpaid"},
                ],
            }
            for b in billers
        ]

    if category_slug in {"cable", "data", "airtime", "internet"}:
        providers = []
        if category_slug == "cable":
            for slug, name in _CABLE_TYPES.items():
                providers.append(
                    {
                        "id": slug,
                        "name": name,
                        "type": "cable",
                        "logoUrl": _logo_for(name),
                        "options": [],
                    }
                )
        else:
            for slug, name in _TELCO_NAMES.items():
                providers.append(
                    {
                        "id": slug,
                        "name": name,
                        "type": category_slug,
                        "logoUrl": _logo_for(name),
                        "options": [],
                    }
                )
        return providers

    return []

@router.get("/billers/{biller_code}/items")
async def list_biller_items(
    biller_code: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get Items (Plans) for a specific Biller.
    """
    service_kind = await _resolve_service_kind(biller_code)

    try:
        payload = await nomba_service.list_biller_products(biller_id=biller_code)
        products = nomba_service.extract_biller_products(payload)
    except NombaAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch biller products: {exc}")

    if service_kind == "electricity":
        return [
            {
                "item_code": product.get("slug"),
                "item_name": product.get("name"),
                "type": product.get("type") or "Electricity",
                "amount": None,
                "minimum_amount": None,
                "maximum_amount": None,
                "currency": "NGN",
            }
            for product in products
        ]

    if service_kind == "cable":
        return [
            {
                "item_code": product.get("subScriptionType") or product.get("slug") or product.get("name"),
                "item_name": product.get("subScriptionType") or product.get("name"),
                "type": "cable",
                "amount": (product.get("amount") / 100.0) if product.get("amount") is not None else None,
                "minimum_amount": (product.get("minimum_amount") / 100.0) if product.get("minimum_amount") is not None else None,
                "maximum_amount": (product.get("maximum_amount") / 100.0) if product.get("maximum_amount") is not None else None,
                "currency": "NGN",
            }
            for product in products
        ]

    if service_kind == "telco":
        return [
            {
                "item_code": product.get("plan") or product.get("slug") or str(product.get("amount")),
                "item_name": product.get("plan") or product.get("name") or f"NGN {product.get('amount')}",
                "type": "data",
                "amount": (product.get("amount") / 100.0) if product.get("amount") is not None else None,
                "minimum_amount": (product.get("minimum_amount") / 100.0) if product.get("minimum_amount") is not None else None,
                "maximum_amount": (product.get("maximum_amount") / 100.0) if product.get("maximum_amount") is not None else None,
                "currency": "NGN",
            }
            for product in products
        ]

    return []

@router.post("/verify", response_model=ServiceVerifyResponse)
async def verify_service(
    data: ServiceVerifyRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Verify SmartCard/Meter Number.
    """
    service_kind = await _resolve_service_kind(data.serviceId)

    if service_kind == "electricity":
        try:
            result = await nomba_service.lookup_electricity_customer(
                disco=data.serviceId,
                customer_id=data.accountNumber,
            )
        except NombaAPIError as exc:
            raise HTTPException(status_code=400, detail=f"Validation failed: {exc}")
        account_name = result.get("data") or data.accountNumber
        return {"valid": True, "accountName": str(account_name)}

    if service_kind == "cable":
        try:
            result = await nomba_service.lookup_cabletv_customer(
                cable_tv_type=data.serviceId,
                customer_id=data.accountNumber,
            )
        except NombaAPIError as exc:
            raise HTTPException(status_code=400, detail=f"Validation failed: {exc}")
        account_name = result.get("data") or data.accountNumber
        return {"valid": True, "accountName": str(account_name)}

    if service_kind == "telco":
        normalized_phone = normalize_phone_number(data.accountNumber)
        return {
            "valid": True,
            "accountName": normalized_phone or data.accountNumber,
        }

    provider_slug = data.provider
    categories = ["electricity", "airtime", "data", "cable", "internet"]
    if provider_slug:
        p_lower = provider_slug.lower()
        if p_lower in categories or "electric" in p_lower:
            provider_slug = None

    if not provider_slug:
        return {
            "valid": True,
            "accountName": data.accountNumber,
        }

    try:
        result = await nomba_service.validate_bill_customer(
            provider_slug=provider_slug, customer_number=data.accountNumber
        )
    except NombaAPIError as exc:
        raise HTTPException(status_code=400, detail=f"Validation failed: {exc}")

    account_name = result.get("data") or data.accountNumber
    return {
        "valid": True,
        "accountName": account_name,
    }

@router.post("/validate-phone", response_model=PhoneValidationResponse)
async def validate_phone_network(
    data: PhoneValidationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Validate Phone Number and Network (Local Prefix Check).
    """
    normalized = normalize_phone_number(data.phoneNumber)
    detected_net = get_network_from_phone(normalized)
    
    if not detected_net:
        return {
            "valid": False,
            "network": None,
            "formatted": normalized,
            "message": "Invalid or Unknown Network Prefix"
        }
        
    if data.network:
        user_net = data.network.lower()
        if detected_net not in user_net and user_net not in detected_net:
             return {
                "valid": False,
                "network": detected_net,
                "formatted": normalized,
                "message": f"Number belongs to {detected_net.upper()}, not {data.network}"
            }
            
    return {
        "valid": True,
        "network": detected_net,
        "formatted": normalized,
        "message": "Valid Number"
    }

@router.post("/pay")
async def pay_service(
    data: ServicePayRequest,
    current_user: User = Depends(set_tenant_context),
    unit = Depends(get_optional_unit),
    db: AsyncSession = Depends(get_db)
):
    """
    Pay utility bill from Nomba wallet.
    """
    verify_transaction_pin(current_user, data.transaction_pin)

    wallet_profile = (
        await db.execute(select(WalletProfile).where(WalletProfile.user_id == current_user.id))
    ).scalars().first()
    wallet_status = _map_wallet_status(wallet_profile)
    if wallet_status != "active":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "wallet_required",
                "message": "Utility payments require an active Nomba wallet.",
                "wallet_status": wallet_status,
            },
        )

    if not data.accountNumber:
        raise HTTPException(status_code=400, detail="Account Number (customer identifier) is required")
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")

    service_kind = await _resolve_service_kind(data.serviceId)
    selected_product = None
    amount_reference_product: Dict[str, Any] = {}

    if service_kind == "electricity":
        meter_type = data.providerId or "prepaid"
        selected_product = {
            "slug": _normalize_service_key(meter_type),
            "name": meter_type.title(),
            "type": "Electricity",
        }
    elif service_kind in {"cable", "telco"} and data.providerId:
        try:
            payload = await nomba_service.list_biller_products(biller_id=data.serviceId)
            products = nomba_service.extract_biller_products(payload)
        except NombaAPIError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch service products: {exc}")
        if not products:
            raise HTTPException(status_code=400, detail="No products available for selected service provider")
        try:
            selected_product = select_service_product(products, data.providerId)
            amount_reference_product = selected_product
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    elif service_kind == "telco":
        selected_product = None
    else:
        try:
            payload = await nomba_service.list_biller_products(biller_id=data.serviceId)
            products = nomba_service.extract_biller_products(payload)
        except NombaAPIError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch service products: {exc}")
        if products and data.providerId:
            try:
                selected_product = select_service_product(products, data.providerId)
                amount_reference_product = selected_product
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        elif products:
            selected_product = products[0]
            amount_reference_product = selected_product

    try:
        amount_kobo, used_legacy_kobo = resolve_service_amount_kobo(
            data.amount,
            amount_reference_product,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if used_legacy_kobo and selected_product:
        logger.warning(
            "Accepted legacy kobo amount for utility payment (biller=%s, product=%s)",
            data.serviceId,
            selected_product.get("slug"),
        )

    try:
        bill_type = "Airtime"
        if service_kind == "electricity":
            bill_type = "Electricity"
        elif service_kind == "cable":
            bill_type = "CableTV"
        elif service_kind == "telco" and data.providerId:
            bill_type = "Data"

        result = await process_external_utility_payment(
            current_user,
            unit.id if unit else None,
            amount_kobo,
            data.serviceId,
            (selected_product or {}).get("slug") or data.providerId or data.serviceId,
            data.accountNumber,
            db,
            debit_wallet=True,
            provider="nomba_bill",
            product=selected_product or amount_reference_product or None,
            bill_type=bill_type,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Bill Payment Failed: {exc}")

    response = {"status": result["status"], "message": result["message"]}
    if result.get("newBalance") is not None:
        response["new_balance"] = result["newBalance"] / 100.0
    return response
