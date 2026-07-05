from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from core.billing import (
    BILL_BILL_TYPE,
    RENT_BILL_TYPE,
    SERVICE_CHARGE_BILL_TYPE,
    assignment_total_amount_kobo,
    bill_title_prefix,
    display_bill_title,
    infer_bill_type,
    normalize_bill_type,
)
from core.db import get_db
from core.deps import get_current_unit, require_estate_membership
from core.models import Bill, BillAssignment, Estate, HouseholdRole, Unit, User, UserUnit
from core.security import verify_transaction_pin
from core.services.payment_service import process_bill_payment, process_estate_bill_payment, process_rent_payment, process_service_charge_payment
from schemas import BillPayRequest, BillSummaryResponse, BillView, PayBillRequest, RentPayRequest, RentSummaryResponse, ServiceChargePayRequest, ServiceChargeResponse

router = APIRouter(prefix="/bills", tags=["Bills"])


def _bill_type_clause(bill_type: str):
    normalized = normalize_bill_type(bill_type)
    prefixed_pattern = f"{bill_title_prefix(normalized)}%"

    if normalized == RENT_BILL_TYPE:
        return or_(
            Bill.title.like(prefixed_pattern),
            Bill.title.ilike("%rent%"),
        )
    if normalized == SERVICE_CHARGE_BILL_TYPE:
        return or_(
            Bill.title.like(prefixed_pattern),
            Bill.title.ilike("%service charge%"),
        )

    return or_(
        Bill.title.like(prefixed_pattern),
        Bill.title.ilike("%estate bill%"),
        Bill.title.ilike("%property bill%"),
    )


def _serialize_assignment(assignment: BillAssignment) -> dict | None:
    bill_type = infer_bill_type(assignment.bill.title)
    if bill_type not in {BILL_BILL_TYPE, RENT_BILL_TYPE, SERVICE_CHARGE_BILL_TYPE}:
        return None

    return {
        "id": assignment.id,
        "billType": bill_type,
        "billTitle": display_bill_title(assignment.bill.title),
        "billDescription": assignment.bill.description,
        "totalAmount": float(assignment_total_amount_kobo(assignment)) / 100.0,
        "amountPaid": float(assignment.amount_paid or 0) / 100.0,
        "amountLeft": float(max(0, assignment_total_amount_kobo(assignment) - (assignment.amount_paid or 0))) / 100.0,
        "status": assignment.status,
        "dueDate": str(assignment.bill.due_date) if assignment.bill.due_date else None,
    }


@router.get("/service-charge", response_model=ServiceChargeResponse)
async def get_service_charge(
    unit_id: str = None,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db),
):
    if not unit_id:
        stmt = select(UserUnit).where(UserUnit.user_id == current_user.id, UserUnit.is_primary == True)
        link = (await db.execute(stmt)).scalars().first()
        if not link:
            fallback_stmt = select(UserUnit).where(UserUnit.user_id == current_user.id)
            link = (await db.execute(fallback_stmt)).scalars().first()
        if link:
            unit_id = link.unit_id

    if not unit_id:
        return {
            "unit_id": "",
            "total_outstanding": 0.0,
            "amount": 0.0,
            "total_paid": 0.0,
            "bills_count": 0,
            "oldest_due_date": None,
            "status": "paid",
            "currency": "NGN",
        }

    stmt = (
        select(BillAssignment)
        .join(Bill)
        .where(
            BillAssignment.unit_id == unit_id,
            BillAssignment.status != "PAID",
            _bill_type_clause(SERVICE_CHARGE_BILL_TYPE),
        )
        .options(selectinload(BillAssignment.bill))
        .order_by(Bill.due_date.asc())
    )
    assignments = (await db.execute(stmt)).scalars().all()

    if not assignments:
        return {
            "unit_id": unit_id,
            "total_outstanding": 0.0,
            "amount": 0.0,
            "total_paid": 0.0,
            "bills_count": 0,
            "oldest_due_date": None,
            "status": "paid",
            "currency": "NGN",
        }

    total_billed = sum(assignment_total_amount_kobo(a) for a in assignments)
    total_paid = sum(a.amount_paid for a in assignments)
    total_outstanding = max(0, total_billed - total_paid)
    oldest_due_date = assignments[0].bill.due_date

    now = datetime.now(timezone.utc)
    has_overdue = any(a.bill.due_date and a.bill.due_date < now for a in assignments)
    has_partial = any(a.status == "PARTIAL" for a in assignments)

    if has_overdue:
        status = "overdue"
    elif has_partial:
        status = "partial"
    else:
        status = "due"

    return {
        "unit_id": unit_id,
        "total_outstanding": total_outstanding / 100.0,
        "amount": total_outstanding / 100.0,
        "total_paid": total_paid / 100.0,
        "bills_count": len(assignments),
        "oldest_due_date": oldest_due_date,
        "status": status,
        "currency": "NGN",
    }


@router.post("/service-charge/pay", response_model=dict)
async def pay_service_charge(
    data: ServiceChargePayRequest,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db),
):
    verify_transaction_pin(current_user, data.transaction_pin)

    stmt_role = select(UserUnit).where(UserUnit.user_id == current_user.id, UserUnit.unit_id == data.unitId)
    link = (await db.execute(stmt_role)).scalars().first()
    if not link:
        raise HTTPException(status_code=403, detail="You must belong to this unit to pay service charge")

    try:
        amount_kobo = int(data.amount * 100)
        result = await process_service_charge_payment(
            current_user,
            data.unitId,
            amount_kobo,
            db,
            debit_wallet=True,
            provider="nomba_wallet",
            reference_prefix="SVC",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "status": result.get("status", "success"),
        "new_balance": (result.get("new_balance") or 0) / 100.0,
        "bill_status": result.get("bill_status"),
        "remaining_amount": (result.get("remaining_amount") or 0) / 100.0,
        "amount_paid": (result.get("amount_paid") or 0) / 100.0,
        "total_amount": (result.get("total_amount") or 0) / 100.0,
        "applied_assignments": result.get("applied_assignments", 0),
        "fully_paid_assignments": result.get("fully_paid_assignments", 0),
        "applied_assignment_ids": result.get("applied_assignment_ids", []),
        "transactionReference": result.get("transaction_reference"),
    }


@router.get("/rent-config")
async def get_rent_config(
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Estate).where(Estate.id == current_user.estate_id))
    estate = result.scalars().first()

    if not estate:
        raise HTTPException(status_code=404, detail="Estate not found")

    return {
        "enabled": estate.rent_collection_enabled,
        "collection_account_id": None,
    }


@router.get("/rent-details", response_model=RentSummaryResponse)
async def get_rent_details(
    unit_id: str,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Unit).where(Unit.id == unit_id))
    unit = result.scalars().first()

    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    stmt_assign = (
        select(BillAssignment)
        .join(Bill)
        .where(
            BillAssignment.unit_id == unit.id,
            BillAssignment.status != "PAID",
            _bill_type_clause(RENT_BILL_TYPE),
        )
        .options(selectinload(BillAssignment.bill))
        .order_by(Bill.due_date.asc())
    )
    assignments = (await db.execute(stmt_assign)).scalars().all()

    now = datetime.now(timezone.utc)

    if not assignments:
        return {
            "unit_id": unit.id,
            "total_outstanding": 0.0,
            "total_paid": 0.0,
            "bills_count": 0,
            "oldest_due_date": unit.next_rent_due,
            "status": "paid",
            "currency": "NGN",
        }

    total_billed = sum(assignment_total_amount_kobo(a) for a in assignments)
    total_paid = sum(a.amount_paid for a in assignments)
    total_outstanding = total_billed - total_paid
    oldest_due_date = assignments[0].bill.due_date

    has_overdue = any(a.bill.due_date and a.bill.due_date < now for a in assignments)
    has_partial = any(a.status == "PARTIAL" for a in assignments)

    if has_overdue:
        status = "overdue"
    elif has_partial:
        status = "partial"
    else:
        status = "due"

    return {
        "unit_id": unit.id,
        "total_outstanding": total_outstanding / 100.0,
        "total_paid": total_paid / 100.0,
        "bills_count": len(assignments),
        "oldest_due_date": oldest_due_date,
        "status": status,
        "currency": "NGN",
    }


@router.get("/bill", response_model=BillSummaryResponse)
async def get_estate_bill_summary(
    unit_id: str = None,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db),
):
    if not unit_id:
        stmt = select(UserUnit).where(UserUnit.user_id == current_user.id, UserUnit.is_primary == True)
        link = (await db.execute(stmt)).scalars().first()
        if not link:
            fallback_stmt = select(UserUnit).where(UserUnit.user_id == current_user.id)
            link = (await db.execute(fallback_stmt)).scalars().first()
        if link:
            unit_id = link.unit_id

    if not unit_id:
        return {
            "unit_id": "",
            "total_outstanding": 0.0,
            "amount": 0.0,
            "total_paid": 0.0,
            "bills_count": 0,
            "oldest_due_date": None,
            "status": "paid",
            "currency": "NGN",
            "bill_title": None,
            "billTitle": None,
            "bill_description": None,
            "billDescription": None,
        }

    stmt = (
        select(BillAssignment)
        .join(Bill)
        .where(
            BillAssignment.unit_id == unit_id,
            BillAssignment.status != "PAID",
            _bill_type_clause(BILL_BILL_TYPE),
        )
        .options(selectinload(BillAssignment.bill))
        .order_by(Bill.due_date.asc(), Bill.created_at.asc())
    )
    assignments = (await db.execute(stmt)).scalars().all()

    if not assignments:
        return {
            "unit_id": unit_id,
            "total_outstanding": 0.0,
            "amount": 0.0,
            "total_paid": 0.0,
            "bills_count": 0,
            "oldest_due_date": None,
            "status": "paid",
            "currency": "NGN",
            "bill_title": None,
            "billTitle": None,
            "bill_description": None,
            "billDescription": None,
        }

    total_billed = sum(assignment_total_amount_kobo(a) for a in assignments)
    total_paid = sum(a.amount_paid for a in assignments)
    total_outstanding = max(0, total_billed - total_paid)
    oldest_due_date = assignments[0].bill.due_date
    oldest_assignment = assignments[0]

    now = datetime.now(timezone.utc)
    has_overdue = any(a.bill.due_date and a.bill.due_date < now for a in assignments)
    has_partial = any(a.status == "PARTIAL" for a in assignments)

    if has_overdue:
        status = "overdue"
    elif has_partial:
        status = "partial"
    else:
        status = "due"

    title = display_bill_title(oldest_assignment.bill.title)
    description = oldest_assignment.bill.description
    return {
        "unit_id": unit_id,
        "total_outstanding": total_outstanding / 100.0,
        "amount": total_outstanding / 100.0,
        "total_paid": total_paid / 100.0,
        "bills_count": len(assignments),
        "oldest_due_date": oldest_due_date,
        "status": status,
        "currency": "NGN",
        "bill_title": title,
        "billTitle": title,
        "bill_description": description,
        "billDescription": description,
    }


@router.post("/bill/pay", response_model=dict)
async def pay_estate_bill(
    data: BillPayRequest,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db),
):
    verify_transaction_pin(current_user, data.transaction_pin)

    stmt_role = select(UserUnit).where(UserUnit.user_id == current_user.id, UserUnit.unit_id == data.unitId)
    link = (await db.execute(stmt_role)).scalars().first()
    if not link or link.role not in [HouseholdRole.ADMIN, HouseholdRole.SUB_ADMIN]:
        raise HTTPException(status_code=403, detail="Only Household Admin can pay estate bills")

    try:
        amount_kobo = int(data.amount * 100)
        result = await process_estate_bill_payment(
            current_user,
            data.unitId,
            amount_kobo,
            db,
            debit_wallet=True,
            provider="nomba_wallet",
            reference_prefix="BILL",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "new_balance": (result.get("new_balance") or 0) / 100.0,
        "bill_status": result.get("bill_status"),
        "remaining_amount": (result.get("remaining_amount") or 0) / 100.0,
        "amount_paid": (result.get("amount_paid") or 0) / 100.0,
        "total_amount": (result.get("total_amount") or 0) / 100.0,
    }


@router.post("/rent/pay", response_model=dict)
async def pay_rent(
    data: RentPayRequest,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db),
):
    verify_transaction_pin(current_user, data.transaction_pin)

    result = await db.execute(select(Unit).where(Unit.id == data.unitId))
    unit = result.scalars().first()

    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    stmt_role = select(UserUnit).where(UserUnit.user_id == current_user.id, UserUnit.unit_id == unit.id)
    link = (await db.execute(stmt_role)).scalars().first()

    if not link or link.role not in [HouseholdRole.ADMIN, HouseholdRole.SUB_ADMIN]:
        raise HTTPException(status_code=403, detail="Only Household Admin can pay Rent")

    try:
        amount_kobo = int(data.amount * 100)
        result = await process_rent_payment(
            current_user,
            data.unitId,
            amount_kobo,
            db,
            debit_wallet=True,
            provider="nomba_wallet",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "success": result.get("success", True),
        "message": result.get("message", "Payment successful"),
        "new_balance": (result.get("newBalance") or 0) / 100.0,
        "transactionReference": result.get("transactionReference"),
        "remaining_amount": (result.get("remaining_amount", 0) or 0) / 100.0,
    }


@router.get("/", response_model=list[BillView])
async def list_my_bills(
    current_user: User = Depends(require_estate_membership),
    unit=Depends(get_current_unit),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(BillAssignment)
        .join(Bill)
        .order_by(Bill.created_at.desc())
        .options(selectinload(BillAssignment.bill))
    )

    stmt_units = select(UserUnit.unit_id).where(
        UserUnit.user_id == current_user.id,
        UserUnit.role.in_([HouseholdRole.ADMIN, HouseholdRole.SUB_ADMIN]),
    )
    eligible_unit_ids = (await db.execute(stmt_units)).scalars().all()

    if not eligible_unit_ids:
        return []

    query = query.where(BillAssignment.unit_id.in_(eligible_unit_ids))

    if unit:
        if unit.id not in eligible_unit_ids:
            return []
        query = query.where(BillAssignment.unit_id == unit.id)

    assignments = (await db.execute(query)).scalars().all()
    serialized = [_serialize_assignment(assignment) for assignment in assignments]
    return [assignment for assignment in serialized if assignment]


@router.post("/{assignment_id}/pay", response_model=dict)
async def pay_bill_from_wallet(
    assignment_id: str,
    data: PayBillRequest,
    current_user: User = Depends(require_estate_membership),
    db: AsyncSession = Depends(get_db),
):
    verify_transaction_pin(current_user, data.transaction_pin)

    stmt = (
        select(BillAssignment)
        .where(BillAssignment.id == assignment_id)
        .options(selectinload(BillAssignment.bill), selectinload(BillAssignment.unit))
    )
    assignment = (await db.execute(stmt)).scalars().first()

    if not assignment:
        raise HTTPException(status_code=404, detail="Bill not found")

    unit = assignment.unit
    link = await db.execute(select(UserUnit).where(UserUnit.user_id == current_user.id, UserUnit.unit_id == unit.id))
    if not link.scalars().first():
        raise HTTPException(status_code=403, detail="Not authorized for this unit")

    role_check = await db.execute(select(UserUnit).where(UserUnit.user_id == current_user.id, UserUnit.unit_id == unit.id))
    u_link = role_check.scalars().first()
    if not u_link or u_link.role not in [HouseholdRole.ADMIN, HouseholdRole.SUB_ADMIN]:
        raise HTTPException(status_code=403, detail="Only Household Admin can pay bills")

    try:
        amount_kobo = int(data.amount * 100)
        result = await process_bill_payment(
            current_user,
            assignment_id,
            amount_kobo,
            db,
            debit_wallet=True,
            provider="nomba_wallet",
            reference_prefix="ANCH",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "status": result.get("status", "success"),
        "new_balance": (result.get("new_balance") or 0) / 100.0,
        "bill_status": result.get("bill_status"),
        "remaining_amount": (result.get("remaining_amount") or 0) / 100.0,
        "amount_paid": (result.get("amount_paid") or 0) / 100.0,
        "total_amount": (result.get("total_amount") or 0) / 100.0,
    }
