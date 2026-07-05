import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add current directory to path
sys.path.append(os.getcwd())

from sqlalchemy import select
from core.db import engine, AsyncSessionLocal
from core.models import (
    User, Estate, Unit, VisitorInvite, InviteStatus, InviteType, 
    Transaction, WalletHistory, Bill, BillAssignment, Notification, UserUnit
)

async def seed_activity():
    async with AsyncSessionLocal() as db:
        email = "apple@gatenode.com"
        print(f"🌱 Seeding data for {email}...")
        
        # 1. Get User
        user = (await db.execute(select(User).where(User.email == email))).scalars().first()
        if not user:
            print("❌ User not found. Run create_apple_review_account.py first.")
            return
            
        estate_id = user.estate_id
        
        # Get Unit ID via direct query (avoid lazy load error)
        stmt = select(UserUnit).where(UserUnit.user_id == user.id).limit(1)
        user_unit = (await db.execute(stmt)).scalars().first()
        
        if not user_unit:
             print("❌ User has no units linked.")
             return
        unit_id = user_unit.unit_id

        # 2. Add Visitor Invites (Recent)
        print("   -> Creating Visitor Invites...")
        invites = [
            VisitorInvite(
                visitor_name="John Doe (Uber)",
                access_code="UBER01",
                valid_from=datetime.utcnow() - timedelta(hours=2),
                valid_until=datetime.utcnow() + timedelta(hours=22),
                status=InviteStatus.USED, # Used
                invite_type=InviteType.SINGLE,
                user_id=user.id,
                unit_id=unit_id,
                estate_id=estate_id
            ),
            VisitorInvite(
                visitor_name="Jane Smith (Guest)",
                access_code="GUEST1",
                valid_from=datetime.utcnow(),
                valid_until=datetime.utcnow() + timedelta(days=1),
                status=InviteStatus.ACTIVE, # Active
                invite_type=InviteType.SINGLE,
                user_id=user.id,
                unit_id=unit_id,
                estate_id=estate_id
            ),
             VisitorInvite(
                visitor_name="Mike Installer",
                access_code="SVC999",
                valid_from=datetime.utcnow() - timedelta(days=2),
                valid_until=datetime.utcnow() - timedelta(days=1),
                status=InviteStatus.EXPIRED, # Expired
                invite_type=InviteType.SINGLE,
                user_id=user.id,
                unit_id=unit_id,
                estate_id=estate_id
            )
        ]
        for inv in invites:
            db.add(inv)

        # 3. Add Wallet Transaction (Top Up)
        print("   -> Creating Wallet History...")
        wh = WalletHistory(
            unit_id=unit_id, # Actually wallet history might serve units, but user has wallet balance
            amount=500000, # 5,000.00
            description="Wallet Top Up via Card",
            created_at=datetime.utcnow() - timedelta(days=1)
        )
        db.add(wh)
        
        # Update User Balance to look nice
        user.wallet_balance = 750000 # 7,500.00
        db.add(user)
        
        # 4. Add Bill & Payment
        print("   -> Creating Paid Bill...")
        bill = Bill(
            title="Service Charge (January)",
            total_amount=2500000, # 25,000
            due_date=datetime.utcnow() + timedelta(days=15),
            estate_id=estate_id
        )
        db.add(bill)
        await db.flush() # Get ID
        
        assignment = BillAssignment(
            bill_id=bill.id,
            unit_id=unit_id,
            amount_paid=2500000,
            status="PAID"
        )
        db.add(assignment)
        
        # 5. Add Notification
        print("   -> Creating Notification...")
        notif = Notification(
            title="Welcome to Resident Client",
            message="Your account is fully set up. Enjoy seamless access control.",
            user_id=user.id,
            is_read=True
        )
        db.add(notif)
        
        await db.commit()
        print("✅ Seeding Complete!")

if __name__ == "__main__":
    asyncio.run(seed_activity())
