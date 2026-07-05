import logging
import json
import uuid
from datetime import datetime, timezone

from core.billing import (
    BILL_BILL_TYPE,
    RENT_BILL_TYPE,
    SERVICE_CHARGE_BILL_TYPE,
    advance_cycle_date,
    assignment_total_amount_kobo,
    bill_title_prefix,
    display_bill_title,
    infer_bill_type,
)
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from core.models import (
    User,
    Unit,
    BillAssignment,
    WalletHistory,
    Transaction,
    Bill,
    HouseholdRole,
    UserUnit,
    WalletProfile,
    RecurringBillingSetup,
    PaymentAllocation,
)
from core.events import event_manager
from core.notifications import notifications
from core.nomba import nomba_service, NombaAPIError
from core.utility_payments import product_price_kobo

logger = logging.getLogger(__name__)


def _payment_reference(reference: str | None = None) -> str:
    return reference or str(uuid.uuid4())


def _clean_utility_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _network_name_from_product(product: dict, product_slug: str | None) -> str | None:
    candidates = [
        product.get("provider"),
        product.get("biller"),
        product.get("network"),
        product.get("operator"),
        product.get("brand"),
    ]
    if product_slug:
        candidates.append(product_slug.split("_", 1)[0].split("-", 1)[0])

    for candidate in candidates:
        text = _clean_utility_text(candidate)
        if text:
            return text.upper()
    return None


def _utility_transaction_description(
    *,
    bill_type: str,
    friendly_name: str,
    product: dict,
    product_slug: str | None,
    customer_id: str,
) -> str:
    customer = _clean_utility_text(customer_id) or "customer"
    name = _clean_utility_text(friendly_name) or "Utility Bill"
    kind = (bill_type or "").lower()

    if kind == "airtime":
        network = _network_name_from_product(product, product_slug)
        service = f"{network} Airtime" if network else name
        return f"Airtime: {service} for {customer}"

    if kind == "data":
        network = _network_name_from_product(product, product_slug)
        service = f"{network} Data" if network and network.lower() not in name.lower() else name
        return f"Data: {service} for {customer}"

    if kind == "electricity":
        return f"Electricity: {name} for meter {customer}"

    if kind in {"television", "cabletv", "cable"}:
        return f"Cable TV: {name} for smartcard {customer}"

    return f"{name} for {customer}"


def _rent_bill_clause():
    prefixed_pattern = f"{bill_title_prefix(RENT_BILL_TYPE)}%"
    return or_(
        Bill.title.like(prefixed_pattern),
        Bill.title.ilike("%rent%"),
    )


def _service_charge_bill_clause():
    prefixed_pattern = f"{bill_title_prefix(SERVICE_CHARGE_BILL_TYPE)}%"
    return or_(
        Bill.title.like(prefixed_pattern),
        Bill.title.ilike("%service charge%"),
    )


def _estate_bill_clause():
    prefixed_pattern = f"{bill_title_prefix(BILL_BILL_TYPE)}%"
    return or_(
        Bill.title.like(prefixed_pattern),
        Bill.title.ilike("%estate bill%"),
        Bill.title.ilike("%property bill%"),
    )

async def process_rent_payment(
    user: User,
    unit_id: str,
    amount: int,
    db: AsyncSession,
    *,
    debit_wallet: bool = True,
    provider: str = "wallet",
    reference: str | None = None,
):
    """
    Process rent payment from wallet.
    amount: Amount in KOBO.
    """
    # 1. Get Unit
    result = await db.execute(select(Unit).where(Unit.id == unit_id))
    unit = result.scalars().first()
    
    if not unit:
        raise ValueError("Unit not found")

    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero")

    # Validate the oldest outstanding rent assignment before any wallet debit.
    stmt_assign = (
        select(BillAssignment)
        .join(Bill)
        .where(
            BillAssignment.unit_id == unit_id,
            BillAssignment.status != "PAID",
            _rent_bill_clause(),
        )
        .options(selectinload(BillAssignment.bill))
        .order_by(Bill.due_date.asc())
    )
    assignment = (await db.execute(stmt_assign)).scalars().first()

    if not assignment:
        raise ValueError("No outstanding rent bills found")

    assignment_total = assignment_total_amount_kobo(assignment)
    amount_left = assignment_total - assignment.amount_paid
    if amount > amount_left:
        raise ValueError(f"Payment ({amount/100}) exceeds outstanding balance ({amount_left/100})")

    ref = _payment_reference(reference)
    new_balance = user.wallet_balance

    if debit_wallet:
        if user.wallet_balance < amount:
            raise ValueError("Insufficient wallet balance")
        user.wallet_balance -= amount
        new_balance = user.wallet_balance

    # Apply payment to the oldest outstanding rent assignment only.
    assignment.amount_paid += amount
    if assignment.amount_paid >= assignment_total:
        assignment.status = "PAID"
        await _update_unit_next_rent_due_from_assignment(unit, assignment, db)
    else:
        assignment.status = "PARTIAL"

    remaining_amount = assignment_total - assignment.amount_paid

    # 5. Log History
    if debit_wallet:
        hist = WalletHistory(
            unit_id=unit.id,
            amount=-amount,
            description="Rent Payment"
        )
        db.add(hist)
    
    # 6. Log Transaction
    txn = Transaction(
        reference=ref,
        provider=provider,
        amount=amount,
        status="success",
        user_id=user.id,
        unit_id=unit.id,
        description="Rent Payment",
        transaction_type="Debit"
    )
    db.add(txn)
    
    await db.commit()
    
    # SSE: Notify Wallet Update
    if debit_wallet:
        await event_manager.publish("wallet:balance_updated", {
            "new_balance": new_balance / 100.0,
            "old_balance": (new_balance + amount) / 100.0,
            "change_amount": amount / 100.0,
            "change_type": "debit",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, user.id)
    
    # SSE: Notify Transaction
    if debit_wallet:
        await db.refresh(txn)
        await event_manager.publish("wallet:transaction_created", {
            "transaction_id": txn.id,
            "amount": amount / 100.0,
            "type": "debit",
            "description": "Rent Payment",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, user.id)
    
    # Push Notification
    try:
        await notifications.send_service_payment_success(db, user.id, amount, "House Rent", ref, unit_id=unit.id)
    except Exception as e:
        print(f"Failed to send Push Notification for Rent: {e}")
    
    return {
        "success": True,
        "message": "Rent payment successful",
        "transactionReference": ref,
        "newBalance": new_balance,
        "remaining_amount": remaining_amount
    }


def _assignment_service_fee_totals(assignment: BillAssignment) -> tuple[int, int]:
    assignment_total = assignment_total_amount_kobo(assignment)
    configured_fee = getattr(assignment, "service_fee_amount", None)
    if configured_fee is None:
        configured_fee = getattr(assignment, "app_charge_amount", None)
    service_fee_total = max(0, min(assignment_total, int(configured_fee or 0)))

    configured_net = getattr(assignment, "estate_net_amount", None)
    if configured_net is None:
        estate_net_total = max(0, assignment_total - service_fee_total)
    else:
        estate_net_total = max(0, min(assignment_total, int(configured_net or 0)))

    if service_fee_total + estate_net_total != assignment_total:
        estate_net_total = max(0, assignment_total - service_fee_total)
    return service_fee_total, estate_net_total


def _component_paid(component_total: int, paid_amount: int, assignment_total: int) -> int:
    if assignment_total <= 0 or component_total <= 0 or paid_amount <= 0:
        return 0
    if paid_amount >= assignment_total:
        return component_total
    return min(component_total, (paid_amount * component_total) // assignment_total)


def _service_charge_payment_plan(assignment: BillAssignment, payment_amount: int) -> dict:
    assignment_total = assignment_total_amount_kobo(assignment)
    paid_before = int(assignment.amount_paid or 0)
    paid_after = min(assignment_total, paid_before + payment_amount)
    service_fee_total, _estate_net_total = _assignment_service_fee_totals(assignment)
    service_fee_before = _component_paid(service_fee_total, paid_before, assignment_total)
    service_fee_after = _component_paid(service_fee_total, paid_after, assignment_total)
    service_fee_amount = max(0, service_fee_after - service_fee_before)
    return {
        "assignment": assignment,
        "gross_amount": payment_amount,
        "service_fee_amount": service_fee_amount,
        "estate_net_amount": max(0, payment_amount - service_fee_amount),
    }


async def _prepare_service_charge_split(
    *,
    user: User,
    unit: Unit,
    plans: list[dict],
    amount: int,
    db: AsyncSession,
    debit_wallet: bool,
    provider: str,
    transfer_reference: str,
    description: str,
) -> tuple[Transaction, list[dict], int]:
    total_service_fee = sum(int(plan["service_fee_amount"] or 0) for plan in plans)
    total_estate = sum(int(plan["estate_net_amount"] or 0) for plan in plans)

    txn = Transaction(
        reference=transfer_reference,
        provider=provider,
        amount=amount,
        status="success",
        user_id=user.id,
        unit_id=unit.id,
        description=description,
        transaction_type="Debit",
        metadata_json=json.dumps(
            {
                "payment_type": "service_charge",
                "gross_amount": amount,
                "service_fee_amount": total_service_fee,
                "estate_net_amount": total_estate,
            }
        ),
    )
    db.add(txn)
    await db.flush()

    for plan in plans:
        assignment = plan["assignment"]
        db.add(
            PaymentAllocation(
                transaction_id=txn.id,
                bill_assignment_id=assignment.id,
                bill_id=assignment.bill_id,
                estate_id=assignment.bill.estate_id,
                unit_id=unit.id,
                gross_amount=int(plan["gross_amount"] or 0),
                service_fee_amount=int(plan["service_fee_amount"] or 0),
                estate_net_amount=int(plan["estate_net_amount"] or 0),
                allocation_status="success",
                payment_reference=transfer_reference,
            )
        )

    await db.commit()
    return txn, [], total_service_fee + total_estate


async def _mark_service_charge_allocations(
    db: AsyncSession,
    *,
    transaction_id: str,
    status: str,
) -> None:
    rows = (
        await db.execute(
            select(PaymentAllocation).where(PaymentAllocation.transaction_id == transaction_id)
        )
    ).scalars().all()
    for row in rows:
        row.allocation_status = status


async def _finalize_service_charge_payment(
    *,
    user: User,
    unit: Unit,
    plans: list[dict],
    amount: int,
    total_outstanding: int,
    db: AsyncSession,
    debit_wallet: bool,
    provider: str,
    transfer_reference: str,
    description: str,
    receipt_title: str,
    applied_assignment_ids: list[str],
) -> dict:
    new_balance = user.wallet_balance
    if debit_wallet and user.wallet_balance < amount:
        raise ValueError("Insufficient wallet balance")

    txn, _transfers, _split_amount = await _prepare_service_charge_split(
        user=user,
        unit=unit,
        plans=plans,
        amount=amount,
        db=db,
        debit_wallet=debit_wallet,
        provider=provider,
        transfer_reference=transfer_reference,
        description=description,
    )

    if debit_wallet:
        new_balance = user.wallet_balance - amount
        user.wallet_balance = new_balance
        successful_transfer_amount = amount
    else:
        successful_transfer_amount = amount

    fully_paid_assignments = 0
    for plan in plans:
        assignment = plan["assignment"]
        payment_to_apply = int(plan["gross_amount"] or 0)
        assignment_total = assignment_total_amount_kobo(assignment)
        assignment.amount_paid = int(assignment.amount_paid or 0) + payment_to_apply
        if assignment.amount_paid >= assignment_total:
            assignment.status = "PAID"
            fully_paid_assignments += 1
        else:
            assignment.status = "PARTIAL"

    txn.status = "success"
    await _mark_service_charge_allocations(db, transaction_id=txn.id, status="success")

    if debit_wallet:
        db.add(
            WalletHistory(
                unit_id=unit.id,
                amount=-amount,
                description=description,
            )
        )

    await db.commit()

    if debit_wallet:
        await event_manager.publish("wallet:balance_updated", {
            "new_balance": new_balance / 100.0,
            "old_balance": (new_balance + successful_transfer_amount) / 100.0,
            "change_amount": successful_transfer_amount / 100.0,
            "change_type": "debit",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, user.id)

    try:
        await notifications.send_service_payment_success(
            db,
            user.id,
            amount,
            receipt_title,
            transfer_reference,
            unit_id=unit.id,
        )
    except Exception as e:
        print(f"Failed to send Push Notification for Service Charge: {e}")

    remaining_total_outstanding = total_outstanding - amount

    return {
        "status": "success",
        "new_balance": new_balance,
        "bill_status": "PAID" if remaining_total_outstanding == 0 else "PARTIAL",
        "remaining_amount": max(0, remaining_total_outstanding),
        "amount_paid": amount,
        "total_amount": total_outstanding,
        "applied_assignments": len(applied_assignment_ids),
        "fully_paid_assignments": fully_paid_assignments,
        "applied_assignment_ids": applied_assignment_ids,
        "transaction_reference": transfer_reference,
    }

async def process_bill_payment(
    user: User,
    assignment_id: str,
    amount: int,
    db: AsyncSession,
    *,
    debit_wallet: bool = True,
    provider: str = "wallet",
    reference_prefix: str = "BILL",
    reference: str | None = None,
):
    """
    Process bill payment from wallet.
    amount: Amount in KOBO.
    """
    from sqlalchemy.orm import selectinload
    
    # 1. Get Assignment
    stmt = select(BillAssignment).where(
        BillAssignment.id == assignment_id
    ).options(selectinload(BillAssignment.bill), selectinload(BillAssignment.unit))
    result = await db.execute(stmt)
    assignment = result.scalars().first()
    
    if not assignment:
        raise ValueError("Bill not found")
        
    unit = assignment.unit
    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero")

    assignment_total = assignment_total_amount_kobo(assignment)
    amount_left = assignment_total - assignment.amount_paid
    if amount > amount_left:
         raise ValueError(f"Payment ({amount/100}) exceeds outstanding balance ({amount_left/100})")

    transfer_reference = _payment_reference(reference)
    new_balance = user.wallet_balance
    bill_title = display_bill_title(assignment.bill.title)
    description = f"Paid Bill: {bill_title}"

    if infer_bill_type(assignment.bill.title) == SERVICE_CHARGE_BILL_TYPE:
        plan = _service_charge_payment_plan(assignment, amount)
        return await _finalize_service_charge_payment(
            user=user,
            unit=unit,
            plans=[plan],
            amount=amount,
            total_outstanding=amount_left,
            db=db,
            debit_wallet=debit_wallet,
            provider=provider,
            transfer_reference=transfer_reference,
            description=description,
            receipt_title=bill_title or "Service Charge",
            applied_assignment_ids=[assignment.id],
        )

    if debit_wallet:
        if user.wallet_balance < amount:
            raise ValueError("Insufficient wallet balance")
        user.wallet_balance -= amount
        new_balance = user.wallet_balance

    # 3. Apply payment to bill
    assignment.amount_paid += amount

    if assignment.amount_paid >= assignment_total:
        assignment.status = "PAID"
        if infer_bill_type(assignment.bill.title) == RENT_BILL_TYPE:
            await _update_unit_next_rent_due_from_assignment(unit, assignment, db)
    else:
        assignment.status = "PARTIAL"

    # 4. Log History
    if debit_wallet:
        hist_bill = WalletHistory(
            unit_id=unit.id,
            amount=-amount,
            description=description,
        )
        db.add(hist_bill)

    txn_bill = Transaction(
        reference=transfer_reference,
        provider=provider,
        amount=amount,
        status="success",
        user_id=user.id,
        unit_id=unit.id,
        description=description,
        transaction_type="Debit"
    )
    db.add(txn_bill)

        
    await db.commit()
    
    # SSE Notifications
    if debit_wallet:
        await event_manager.publish("wallet:balance_updated", {
            "new_balance": new_balance / 100.0,
            "old_balance": (new_balance + amount) / 100.0,
            "change_amount": amount / 100.0,
            "change_type": "debit",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, user.id)
    
    # Push Notification
    try:
        await notifications.send_service_payment_success(db, user.id, amount, bill_title, transfer_reference, unit_id=unit.id)
    except Exception as e:
        print(f"Failed to send Push Notification for Bill: {e}")
    
    remaining_amount = assignment_total - assignment.amount_paid

    return {
        "status": "success",
        "new_balance": new_balance,
        "bill_status": assignment.status,
        "remaining_amount": max(0, remaining_amount),
        "amount_paid": assignment.amount_paid,
        "total_amount": assignment_total,
    }


async def process_service_charge_payment(
    user: User,
    unit_id: str,
    amount: int,
    db: AsyncSession,
    *,
    debit_wallet: bool = True,
    provider: str = "wallet",
    reference_prefix: str = "SVC",
    reference: str | None = None,
):
    """
    Process a service-charge payment across the oldest unpaid assignments first.
    amount: Amount in KOBO.
    """
    result = await db.execute(select(Unit).where(Unit.id == unit_id))
    unit = result.scalars().first()

    if not unit:
        raise ValueError("Unit not found")

    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero")

    stmt_assign = (
        select(BillAssignment)
        .join(Bill)
        .where(
            BillAssignment.unit_id == unit_id,
            BillAssignment.status != "PAID",
            _service_charge_bill_clause(),
        )
        .options(selectinload(BillAssignment.bill))
        .order_by(Bill.due_date.asc(), Bill.created_at.asc())
    )
    assignments = (await db.execute(stmt_assign)).scalars().all()

    if not assignments:
        raise ValueError("No outstanding service charge bills found")

    total_outstanding = sum(
        max(0, assignment_total_amount_kobo(assignment) - (assignment.amount_paid or 0))
        for assignment in assignments
    )
    if amount > total_outstanding:
        raise ValueError(f"Payment ({amount/100}) exceeds outstanding balance ({total_outstanding/100})")

    transfer_reference = _payment_reference(reference)
    remaining_to_apply = amount
    applied_assignment_ids: list[str] = []
    last_applied_assignment = None
    plans: list[dict] = []

    for assignment in assignments:
        if remaining_to_apply <= 0:
            break

        assignment_total = assignment_total_amount_kobo(assignment)
        amount_left = max(0, assignment_total - (assignment.amount_paid or 0))
        if amount_left <= 0:
            continue

        payment_to_apply = min(remaining_to_apply, amount_left)
        plans.append(_service_charge_payment_plan(assignment, payment_to_apply))
        remaining_to_apply -= payment_to_apply
        applied_assignment_ids.append(assignment.id)
        last_applied_assignment = assignment

    if not last_applied_assignment:
        raise ValueError("No outstanding service charge bills found")

    if len(applied_assignment_ids) == 1:
        receipt_title = display_bill_title(last_applied_assignment.bill.title)
        description = f"Paid Bill: {receipt_title}"
    else:
        description = "Paid Bill: Service Charge payment"
        receipt_title = "Service Charge"

    return await _finalize_service_charge_payment(
        user=user,
        unit=unit,
        plans=plans,
        amount=amount,
        total_outstanding=total_outstanding,
        db=db,
        debit_wallet=debit_wallet,
        provider=provider,
        transfer_reference=transfer_reference,
        description=description,
        receipt_title=receipt_title,
        applied_assignment_ids=applied_assignment_ids,
    )


async def process_estate_bill_payment(
    user: User,
    unit_id: str,
    amount: int,
    db: AsyncSession,
    *,
    debit_wallet: bool = True,
    provider: str = "wallet",
    reference_prefix: str = "BILL",
    reference: str | None = None,
):
    """
    Process a manual estate bill payment across the oldest unpaid assignments first.
    amount: Amount in KOBO.
    """
    result = await db.execute(select(Unit).where(Unit.id == unit_id))
    unit = result.scalars().first()

    if not unit:
        raise ValueError("Unit not found")

    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero")

    stmt_assign = (
        select(BillAssignment)
        .join(Bill)
        .where(
            BillAssignment.unit_id == unit_id,
            BillAssignment.status != "PAID",
            _estate_bill_clause(),
        )
        .options(selectinload(BillAssignment.bill))
        .order_by(Bill.due_date.asc(), Bill.created_at.asc())
    )
    assignments = (await db.execute(stmt_assign)).scalars().all()

    if not assignments:
        raise ValueError("No outstanding bills found")

    total_outstanding = sum(
        max(0, assignment_total_amount_kobo(assignment) - (assignment.amount_paid or 0))
        for assignment in assignments
    )
    if amount > total_outstanding:
        raise ValueError(f"Payment ({amount/100}) exceeds outstanding balance ({total_outstanding/100})")

    transfer_reference = _payment_reference(reference)
    new_balance = user.wallet_balance

    if debit_wallet:
        if user.wallet_balance < amount:
            raise ValueError("Insufficient wallet balance")
        user.wallet_balance -= amount
        new_balance = user.wallet_balance

    remaining_to_apply = amount
    applied_assignment_ids: list[str] = []
    last_applied_assignment = None

    for assignment in assignments:
        if remaining_to_apply <= 0:
            break

        assignment_total = assignment_total_amount_kobo(assignment)
        amount_left = max(0, assignment_total - (assignment.amount_paid or 0))
        if amount_left <= 0:
            continue

        payment_to_apply = min(remaining_to_apply, amount_left)
        assignment.amount_paid += payment_to_apply
        if assignment.amount_paid >= assignment_total:
            assignment.status = "PAID"
        else:
            assignment.status = "PARTIAL"

        remaining_to_apply -= payment_to_apply
        applied_assignment_ids.append(assignment.id)
        last_applied_assignment = assignment

    if not last_applied_assignment:
        raise ValueError("No outstanding bills found")

    if len(applied_assignment_ids) == 1:
        receipt_title = display_bill_title(last_applied_assignment.bill.title)
        description = f"Paid Bill: {receipt_title}"
    else:
        description = "Paid Bill: Estate Bill payment"
        receipt_title = "Estate Bill"

    if debit_wallet:
        hist_bill = WalletHistory(
            unit_id=unit.id,
            amount=-amount,
            description=description,
        )
        db.add(hist_bill)

    txn_bill = Transaction(
        reference=transfer_reference,
        provider=provider,
        amount=amount,
        status="success",
        user_id=user.id,
        unit_id=unit.id,
        description=description,
        transaction_type="Debit",
    )
    db.add(txn_bill)

    await db.commit()

    if debit_wallet:
        await event_manager.publish("wallet:balance_updated", {
            "new_balance": new_balance / 100.0,
            "old_balance": (new_balance + amount) / 100.0,
            "change_amount": amount / 100.0,
            "change_type": "debit",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, user.id)

    try:
        await notifications.send_service_payment_success(
            db,
            user.id,
            amount,
            receipt_title,
            transfer_reference,
            unit_id=unit.id,
        )
    except Exception as e:
        print(f"Failed to send Push Notification for Estate Bill: {e}")

    remaining_total_outstanding = total_outstanding - amount

    return {
        "status": "success",
        "new_balance": new_balance,
        "bill_status": "PAID" if remaining_total_outstanding == 0 else "PARTIAL",
        "remaining_amount": max(0, remaining_total_outstanding),
        "amount_paid": amount,
        "total_amount": total_outstanding,
        "applied_assignment_ids": applied_assignment_ids,
        "transaction_reference": transfer_reference,
    }


async def _update_unit_next_rent_due_from_assignment(
    unit: Unit,
    assignment: BillAssignment,
    db: AsyncSession,
) -> None:
    bill = assignment.bill
    if not bill or not bill.recurring_setup_id:
        return

    setup_stmt = select(RecurringBillingSetup).where(RecurringBillingSetup.id == bill.recurring_setup_id)
    setup = (await db.execute(setup_stmt)).scalars().first()
    if not setup:
        return

    reference_due = bill.cycle_due_date or bill.due_date
    if reference_due is None:
        return

    candidate_due = advance_cycle_date(reference_due, setup.duration)
    if unit.next_rent_due is None or candidate_due > unit.next_rent_due:
        unit.next_rent_due = candidate_due


async def process_external_utility_payment(
    user: User,
    unit_id: str | None,
    amount: int,
    service_id: str,
    item_code: str,
    customer_id: str,
    db: AsyncSession,
    *,
    debit_wallet: bool = True,
    provider: str = "nomba_bill",
    reference: str | None = None,
    product: dict | None = None,
):
    """
    Fulfill an airtime/data/cable/electricity payment through Nomba Bills API.
    amount: Amount in KOBO.
    """
    if not service_id or not customer_id:
        raise ValueError("Service ID and customer identifier are required")
    if not debit_wallet:
        raise RuntimeError("Direct utility payments are disabled. Use wallet payment.")

    unit = None
    if unit_id:
        result = await db.execute(select(Unit).where(Unit.id == unit_id))
        unit = result.scalars().first()
        if not unit:
            raise ValueError("Unit not found")

    wallet_profile = (
        await db.execute(select(WalletProfile).where(WalletProfile.user_id == user.id))
    ).scalars().first()
    if not wallet_profile or wallet_profile.status != "active" or not wallet_profile.nomba_account_id:
        raise RuntimeError("Active Nomba wallet is required for utility payments.")

    if product is None:
        try:
            products_payload = await nomba_service.list_biller_products(biller_id=service_id)
            products = nomba_service.extract_biller_products(products_payload)
        except NombaAPIError as exc:
            raise RuntimeError(f"Unable to fetch service products: {exc}")

        if not products:
            raise RuntimeError("No service products available for the selected provider.")

        if item_code:
            product = next(
                (
                    candidate
                    for candidate in products
                    if candidate.get("slug") == item_code or candidate.get("id") == item_code
                ),
                None,
            )
            if product is None:
                raise ValueError("Selected product is not available for this service provider")
        else:
            product = products[0]

    minimum_amount = product_price_kobo(product, "minimum_amount")
    maximum_amount = product_price_kobo(product, "maximum_amount")
    if minimum_amount is not None and amount < minimum_amount:
        raise ValueError(f"Payment amount is below the product minimum of NGN {minimum_amount / 100:.2f}")
    if maximum_amount is not None and amount > maximum_amount:
        raise ValueError(f"Payment amount exceeds the product maximum of NGN {maximum_amount / 100:.2f}")

    bill_type = product.get("type") or "Data"
    product_slug = product.get("slug")
    if not product_slug:
        raise RuntimeError("Selected service product has no Nomba slug")
    friendly_name = product.get("name") or "Utility Bill"
    transaction_description = _utility_transaction_description(
        bill_type=bill_type,
        friendly_name=friendly_name,
        product=product,
        product_slug=product_slug,
        customer_id=customer_id,
    )

    ref = _payment_reference(reference)

    txn = Transaction(
        reference=ref,
        provider=provider,
        amount=amount,
        status="pending",
        user_id=user.id,
        unit_id=unit.id if unit else None,
        description=transaction_description,
        transaction_type="Debit",
        metadata_json=json.dumps(
            {
                "bill_type": bill_type,
                "service_id": service_id,
                "product_slug": product_slug,
                "friendly_name": friendly_name,
                "customer_id": customer_id,
            }
        ),
    )
    db.add(txn)
    await db.commit()

    if user.wallet_balance < amount:
        txn.status = "failed"
        db.add(txn)
        await db.commit()
        raise RuntimeError("Insufficient wallet balance")

    try:
        attributes = {
            "reference": txn.reference,
            "amount": amount,
        }

        phone_number = user.phone_number or customer_id

        if bill_type == "Airtime":
            provider_slug = (product_slug or "").split("_")[0]
            if not provider_slug:
                raise RuntimeError("Unable to resolve airtime provider slug")
            attributes.update(
                {
                    "provider": provider_slug,
                    "phoneNumber": customer_id,
                }
            )
        elif bill_type == "Data":
            attributes.update(
                {
                    "phoneNumber": customer_id,
                    "productSlug": product_slug,
                }
            )
        elif bill_type == "Electricity":
            attributes.update(
                {
                    "meterAccountNumber": customer_id,
                    "phoneNumber": phone_number,
                    "productSlug": product_slug,
                }
            )
        elif bill_type in {"Television", "CableTV", "Cable"}:
            attributes.update(
                {
                    "smartCardNumber": customer_id,
                    "phoneNumber": phone_number,
                    "productSlug": product_slug,
                }
            )
        else:
            attributes.update(
                {
                    "productSlug": product_slug,
                    "customerNumber": customer_id,
                }
            )

        res = await nomba_service.initiate_bill_payment(
            bill_type=bill_type,
            attributes=attributes,
            account_id=wallet_profile.nomba_account_id,
            reference=txn.reference,
        )

        if not (res.get("data") or {}).get("id"):
            message = str(res.get("errors") or res)
            raise RuntimeError(message)

        txn.status = "success"
        user.wallet_balance -= amount
        if unit:
            db.add(
                WalletHistory(
                    unit_id=unit.id,
                    amount=-amount,
                    description=transaction_description,
                )
            )
        db.add(txn)
        db.add(user)
        await db.commit()

        new_balance = user.wallet_balance
        if debit_wallet:
            await event_manager.publish("wallet:balance_updated", {
                "new_balance": new_balance / 100.0,
                "change_amount": amount / 100.0,
                "change_type": "debit",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }, user.id)

        try:
            await notifications.send_service_payment_success(
                db,
                user.id,
                amount,
                transaction_description,
                txn.reference,
                unit_id=unit.id if unit else None,
            )
        except Exception as e:
            print(f"Failed to send Push Notification for Utility Payment: {e}")

        return {
            "status": "success",
            "message": "Payment successful",
            "transactionReference": txn.reference,
            "newBalance": new_balance,
            "friendlyName": transaction_description,
        }
    except Exception as api_error:
        txn.status = "failed"
        db.add(txn)
        await db.commit()

        logger.error(
            "Utility payment failed (transaction=%s, biller=%s, product=%s, type=%s, nomba_status=%s): %s",
            txn.reference,
            service_id,
            product_slug,
            bill_type,
            getattr(api_error, "status_code", None),
            api_error,
        )

        try:
            await event_manager.publish("notification", {
                "title": "Utility Payment Failed",
                "message": "Your utility payment could not be processed. Please try again or contact support."
            }, user.id)
        except Exception:
            logger.exception("Failed to publish utility payment failure notification for %s", txn.reference)

        raise RuntimeError(str(api_error))
