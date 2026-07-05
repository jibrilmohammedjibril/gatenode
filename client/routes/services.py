import logging
from typing import List

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
    nomba_cat = _nomba_category(category)
    if not nomba_cat:
        return []

    try:
        biller_payload = await nomba_service.list_billers(category=nomba_cat)
        billers = biller_payload.get("data", [])
    except NombaAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch billers: {exc}")

    billers = [b for b in billers if (b.get("category") or "").lower() == nomba_cat.lower()]

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

    if category.lower() == "electricity":
        grouped_providers = {}
        for b in billers:
            b_name = b.get("name") or ""
            b_name_upper = b_name.upper()
            
            provider_key = None
            logo = None
            for key, url in logo_map.items():
                if key in b_name_upper:
                    provider_key = key
                    logo = url
                    break
            
            if not provider_key:
                provider_key = b_name.split(" ")[0].upper()
                logo = f"https://ui-avatars.com/api/?name={b_name}&background=random&size=128"

            if provider_key not in grouped_providers:
                display_name = (
                    b_name.replace("PostPaid", "")
                    .replace("Postpaid", "")
                    .replace("PrePaid", "")
                    .replace("Prepaid", "")
                    .replace("Electricity", "")
                    .replace("Electric", "")
                    .replace("Elec.", "")
                    .replace("Elec", "")
                    .strip()
                )
                if not display_name.endswith("Electricity") and not ("Electric" in display_name):
                    display_name += " Electricity"
                
                grouped_providers[provider_key] = {
                    "id": None,
                    "name": display_name,
                    "logoUrl": logo,
                    "type": category,
                    "options": []
                }
            
            option_name = "Postpaid" if "post" in b_name.lower() else "Prepaid"
            grouped_providers[provider_key]["options"].append({
                "id": b.get("id"),
                "name": option_name
            })
        
        return sorted(list(grouped_providers.values()), key=lambda x: x["name"])

    providers = []
    for b in billers:
        b_name = b.get("name") or ""
        b_name_upper = b_name.upper()
        logo = None
        for key, url in logo_map.items():
            if key in b_name_upper:
                logo = url
                break
        if not logo:
             logo = f"https://ui-avatars.com/api/?name={b_name}&background=random&size=128"
             
        providers.append({
            "id": b.get("id"),
            "name": b_name,
            "type": category,
            "logoUrl": logo,
            "options": []
        })
    
    return providers

@router.get("/billers/{biller_code}/items")
async def list_biller_items(
    biller_code: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get Items (Plans) for a specific Biller.
    """
    try:
        payload = await nomba_service.list_biller_products(biller_id=biller_code)
        products = nomba_service.extract_biller_products(payload)
    except NombaAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch biller products: {exc}")

    return [
        {
            "item_code": p.get("slug"),
            "item_name": p.get("name"),
            "type": p.get("type"),
            "amount": (p.get("minimum_amount") / 100.0) if p.get("minimum_amount") is not None else None,
            "minimum_amount": (p.get("minimum_amount") / 100.0) if p.get("minimum_amount") is not None else None,
            "maximum_amount": (p.get("maximum_amount") / 100.0) if p.get("maximum_amount") is not None else None,
            "currency": p.get("currency", "NGN"),
        }
        for p in products
    ]

@router.post("/verify", response_model=ServiceVerifyResponse)
async def verify_service(
    data: ServiceVerifyRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Verify SmartCard/Meter Number.
    """
    provider_slug = data.provider
    categories = ["electricity", "airtime", "data", "cable", "internet"]
    if provider_slug:
        p_lower = provider_slug.lower()
        if p_lower in categories or "electric" in p_lower:
            provider_slug = None

    if not provider_slug:
        try:
            payload = await nomba_service.list_biller_products(biller_id=data.serviceId)
            products = nomba_service.extract_biller_products(payload)
        except NombaAPIError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch products for validation: {exc}")
        if not products:
            raise HTTPException(status_code=400, detail="No products found for selected provider")
        provider_slug = products[0]["slug"]

    try:
        result = await nomba_service.validate_bill_customer(
            provider_slug=provider_slug, customer_number=data.accountNumber
        )
    except NombaAPIError as exc:
        raise HTTPException(status_code=400, detail=f"Validation failed: {exc}")

    account_name = (result.get("data") or {}).get("customerName") or data.accountNumber
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

    selected_product_code = data.providerId
    categories = ["electricity", "airtime", "data", "cable", "internet"]
    if selected_product_code:
        p_lower = selected_product_code.lower()
        if p_lower in categories or "electric" in p_lower:
            selected_product_code = None

    try:
        payload = await nomba_service.list_biller_products(biller_id=data.serviceId)
        products = nomba_service.extract_biller_products(payload)
    except NombaAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch service products: {exc}")
    if not products:
        raise HTTPException(status_code=400, detail="No products available for selected service provider")

    try:
        selected_product = select_service_product(products, selected_product_code)
        amount_kobo, used_legacy_kobo = resolve_service_amount_kobo(data.amount, selected_product)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if used_legacy_kobo:
        logger.warning(
            "Accepted legacy kobo amount for utility payment (biller=%s, product=%s)",
            data.serviceId,
            selected_product.get("slug"),
        )

    try:
        result = await process_external_utility_payment(
            current_user,
            unit.id if unit else None,
            amount_kobo,
            data.serviceId,
            selected_product["slug"],
            data.accountNumber,
            db,
            debit_wallet=True,
            provider="nomba_bill",
            product=selected_product,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Bill Payment Failed: {exc}")

    response = {"status": result["status"], "message": result["message"]}
    if result.get("newBalance") is not None:
        response["new_balance"] = result["newBalance"] / 100.0
    return response
