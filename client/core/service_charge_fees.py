from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.billing import duration_months
from core.config import settings
from core.models import ServiceChargeFeeConfig


RESIDENT_PAYS_ALL = "resident_pays_all"
ESTATE_ABSORBS_ALL = "estate_absorbs_all"
SPLIT_50_50 = "split_50_50"
SUPPORTED_ALLOCATION_MODES = {RESIDENT_PAYS_ALL, ESTATE_ABSORBS_ALL, SPLIT_50_50}


@dataclass(frozen=True)
class ServiceChargeFeeBreakdown:
    base_amount: int
    total_fee_amount: int
    resident_fee_amount: int
    estate_absorbed_amount: int
    resident_total_amount: int
    estate_net_amount: int
    allocation_mode: str


def normalize_allocation_mode(value: str | None) -> str:
    normalized = (value or RESIDENT_PAYS_ALL).strip().lower()
    if normalized not in SUPPORTED_ALLOCATION_MODES:
        raise ValueError("Unsupported service charge allocation mode")
    return normalized


def calculate_service_charge_fee_breakdown(
    *,
    base_amount: int,
    duration: str | None,
    monthly_fee_amount: int,
    discount_amount: int = 0,
    allocation_mode: str | None = None,
) -> ServiceChargeFeeBreakdown:
    base_amount = max(0, int(base_amount or 0))
    months = duration_months(duration or "monthly")
    total_fee = max(0, int(monthly_fee_amount or 0) * months - int(discount_amount or 0))
    mode = normalize_allocation_mode(allocation_mode)

    if mode == ESTATE_ABSORBS_ALL:
        resident_fee = 0
        estate_absorbed = min(base_amount, total_fee)
    elif mode == SPLIT_50_50:
        resident_fee = (total_fee + 1) // 2
        estate_absorbed = min(base_amount, total_fee - resident_fee)
    else:
        resident_fee = total_fee
        estate_absorbed = 0

    resident_total = base_amount + resident_fee
    estate_net = max(0, base_amount - estate_absorbed)
    return ServiceChargeFeeBreakdown(
        base_amount=base_amount,
        total_fee_amount=resident_fee + estate_absorbed,
        resident_fee_amount=resident_fee,
        estate_absorbed_amount=estate_absorbed,
        resident_total_amount=resident_total,
        estate_net_amount=estate_net,
        allocation_mode=mode,
    )


async def load_service_charge_fee_config(db: AsyncSession, estate_id: str | None) -> ServiceChargeFeeConfig | None:
    stmt = (
        select(ServiceChargeFeeConfig)
        .where(
            ServiceChargeFeeConfig.is_active.is_(True),
            or_(ServiceChargeFeeConfig.estate_id == estate_id, ServiceChargeFeeConfig.estate_id.is_(None)),
        )
        .order_by(ServiceChargeFeeConfig.estate_id.is_(None).asc(), ServiceChargeFeeConfig.created_at.desc())
    )
    return (await db.execute(stmt)).scalars().first()


async def calculate_estate_service_charge_fee_breakdown(
    db: AsyncSession,
    *,
    estate_id: str,
    base_amount: int,
    duration: str | None,
) -> ServiceChargeFeeBreakdown:
    config = await load_service_charge_fee_config(db, estate_id)
    return calculate_service_charge_fee_breakdown(
        base_amount=base_amount,
        duration=duration,
        monthly_fee_amount=(
            int(config.monthly_fee_amount or 0)
            if config
            else int(settings.SERVICE_CHARGE_DEFAULT_MONTHLY_FEE_KOBO or 0)
        ),
        discount_amount=int(config.discount_amount or 0) if config else 0,
        allocation_mode=config.allocation_mode if config else RESIDENT_PAYS_ALL,
    )
