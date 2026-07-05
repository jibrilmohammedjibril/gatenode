from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from core.db import get_db
from core.models import User, VisitorInvite, InviteStatus, BillAssignment, WalletHistory
from core.deps import get_current_unit, require_estate_membership
from schemas import DashboardResponse
from datetime import datetime

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    current_user: User = Depends(require_estate_membership),
    unit = Depends(get_current_unit),
    db: AsyncSession = Depends(get_db)
):
    """
    Aggregated dashboard data.
    """
    balance = 0
    invites_count = 0
    bills_count = 0
    activities = []
    
    if unit:
        balance = current_user.wallet_balance  # kobo — iOS divides by 100 for display
        
        # Count Active Invites
        stmt_inv = select(func.count(VisitorInvite.id)).where(
            VisitorInvite.unit_id == unit.id,
            VisitorInvite.status == InviteStatus.ACTIVE,
            VisitorInvite.valid_until > datetime.utcnow()
        )
        res_inv = await db.execute(stmt_inv)
        invites_count = res_inv.scalar() or 0
        
        # Count Pending Bills
        stmt_bills = select(func.count(BillAssignment.id)).where(
            BillAssignment.unit_id == unit.id,
            BillAssignment.status != "PAID"
        )
        res_bills = await db.execute(stmt_bills)
        bills_count = res_bills.scalar() or 0
        
        # Recent Activities (Wallet History)
        stmt_hist = select(WalletHistory).where(WalletHistory.unit_id == unit.id).order_by(WalletHistory.created_at.desc()).limit(5)
        res_hist = await db.execute(stmt_hist)
        histories = res_hist.scalars().all()
        
        for h in histories:
            activities.append({
                "id": h.id,
                "title": h.description,
                "type": "wallet",
                "date": str(h.created_at),
                "amount": h.amount / 100.0 # Convert to Naira
            })
            
    # Greeting logic
    hour = datetime.now().hour
    greeting = "Good Morning"
    if 12 <= hour < 18:
        greeting = "Good Afternoon"
    elif hour >= 18:
        greeting = "Good Evening"
        
    return {
        "greeting": f"{greeting}, {current_user.full_name.split(' ')[0]}",
        "wallet_balance": balance / 100.0, # Convert to Naira
        "active_invites_count": invites_count,
        "pending_bills_count": bills_count,
        "recent_activities": activities
    }
