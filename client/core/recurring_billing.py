from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.billing import (
    RECURRING_GENERATION_SOURCE,
    RENT_BILL_TYPE,
    SERVICE_CHARGE_BILL_TYPE,
    advance_cycle_date,
    build_recurring_bill_title,
    cycle_app_charge_kobo,
    normalize_bill_type,
)
from core.models import Bill, BillAssignment, Block, RecurringBillingSetup, Unit, UnitStatus
from core.service_charge_fees import calculate_estate_service_charge_fee_breakdown


DEFAULT_RECURRING_TITLES = {
    RENT_BILL_TYPE: "Rent",
    SERVICE_CHARGE_BILL_TYPE: "Service Charge",
}


async def generate_bill_for_setup(
    db: AsyncSession,
    *,
    setup: RecurringBillingSetup,
    due_date: datetime,
) -> Bill | None:
    bill_type = normalize_bill_type(setup.bill_type)
    existing_stmt = select(Bill).where(
        Bill.recurring_setup_id == setup.id,
        Bill.cycle_due_date == due_date,
    )
    existing_bill = (await db.execute(existing_stmt)).scalars().first()
    if existing_bill:
        return existing_bill

    units_stmt = (
        select(Unit)
        .join(Block)
        .where(
            Block.estate_id == setup.estate_id,
            Unit.status == UnitStatus.OCCUPIED,
        )
        .order_by(Unit.unit_number.asc())
    )
    units = (await db.execute(units_stmt)).scalars().all()
    if not units:
        return None

    is_variable_amount = bill_type == RENT_BILL_TYPE
    base_bill_amount = int(setup.base_amount or 0)
    if bill_type == SERVICE_CHARGE_BILL_TYPE:
        bill_fee_breakdown = await calculate_estate_service_charge_fee_breakdown(
            db,
            estate_id=setup.estate_id,
            base_amount=base_bill_amount,
            duration=setup.duration,
        )
        bill_total_amount = bill_fee_breakdown.resident_total_amount
    else:
        bill_total_amount = 0 if is_variable_amount else base_bill_amount

    try:
        async with db.begin_nested():
            bill = Bill(
                title=build_recurring_bill_title(
                    bill_type,
                    due_date,
                    title=setup.title or DEFAULT_RECURRING_TITLES[bill_type],
                    duration=setup.duration,
                ),
                total_amount=bill_total_amount,
                due_date=due_date,
                generation_source=RECURRING_GENERATION_SOURCE,
                recurring_setup_id=setup.id,
                cycle_due_date=due_date,
                is_variable_amount=is_variable_amount,
                estate_id=setup.estate_id,
            )
            db.add(bill)
            await db.flush()

            for unit in units:
                base_amount = int(unit.rent_amount or 0) if bill_type == RENT_BILL_TYPE else int(setup.base_amount or 0)
                if bill_type == SERVICE_CHARGE_BILL_TYPE:
                    fee_breakdown = await calculate_estate_service_charge_fee_breakdown(
                        db,
                        estate_id=setup.estate_id,
                        base_amount=base_amount,
                        duration=setup.duration,
                    )
                    app_charge_amount = fee_breakdown.resident_fee_amount
                    total_amount = fee_breakdown.resident_total_amount
                    service_fee_amount = fee_breakdown.total_fee_amount
                    resident_service_fee_amount = fee_breakdown.resident_fee_amount
                    estate_absorbed_service_fee_amount = fee_breakdown.estate_absorbed_amount
                    estate_net_amount = fee_breakdown.estate_net_amount
                else:
                    app_charge_amount = 0
                    total_amount = base_amount
                    service_fee_amount = 0
                    resident_service_fee_amount = 0
                    estate_absorbed_service_fee_amount = 0
                    estate_net_amount = base_amount
                db.add(
                    BillAssignment(
                        bill_id=bill.id,
                        unit_id=unit.id,
                        base_amount=base_amount,
                        app_charge_amount=app_charge_amount,
                        service_fee_amount=service_fee_amount,
                        resident_service_fee_amount=resident_service_fee_amount,
                        estate_absorbed_service_fee_amount=estate_absorbed_service_fee_amount,
                        estate_net_amount=estate_net_amount,
                        total_amount=total_amount,
                        amount_paid=0,
                        status="PENDING",
                    )
                )

            await db.flush()
            return bill
    except IntegrityError:
        existing_stmt = select(Bill).where(
            Bill.recurring_setup_id == setup.id,
            Bill.cycle_due_date == due_date,
        )
        return (await db.execute(existing_stmt)).scalars().first()


async def generate_due_cycles(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(timezone.utc)
    stmt = select(RecurringBillingSetup).where(
        RecurringBillingSetup.is_active.is_(True),
        RecurringBillingSetup.auto_renew.is_(True),
        RecurringBillingSetup.next_due_date <= now,
    ).with_for_update(skip_locked=True)
    setups = (await db.execute(stmt)).scalars().all()
    generated_cycles = 0

    for setup in setups:
        while setup.next_due_date and setup.next_due_date <= now:
            due_date = setup.next_due_date
            bill = await generate_bill_for_setup(db, setup=setup, due_date=due_date)
            if bill is not None:
                generated_cycles += 1
            setup.next_due_date = advance_cycle_date(due_date, setup.duration)

    return generated_cycles
