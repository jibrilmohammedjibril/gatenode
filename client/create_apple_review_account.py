import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add current directory to path
sys.path.append(os.getcwd())

from sqlalchemy import select
from core.db import engine, AsyncSessionLocal
from core.models import User, Estate, Unit, UserUnit, Subscription, SubscriptionStatus, SubscriptionPlan, UserRole
from core.security import get_password_hash
import secrets
import string

async def create_apple_account():
    async with AsyncSessionLocal() as db:
        print("🚀 Setting up Apple Review Account...")
        
        # 1. Find or Create Estate & Unit (Essential for App logic)
        estate = (await db.execute(select(Estate).limit(1))).scalars().first()
        if not estate:
            print("❌ No Estate found. Please create an estate first via Admin API.")
            return

        unit = (await db.execute(select(Unit).where(Unit.block_id != None).limit(1))).scalars().first()
        if not unit:
             print("❌ No Unit found. Please create a unit first.")
             return

        email = "apple@gatenode.com"
        password = "Password123!" # Standard review password
        
        # 2. Check if user exists
        user = (await db.execute(select(User).where(User.email == email))).scalars().first()
        
        if not user:
            print(f"Creating new user: {email}")
            user = User(
                email=email,
                full_name="Apple Reviewer",
                hashed_password=get_password_hash(password),
                role=UserRole.RESIDENT,
                is_active=True,
                phone_number="+15550109999",
                estate_id=estate.id
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            
            # Link to Unit
            user_unit = UserUnit(user_id=user.id, unit_id=unit.id, is_primary=True, role="admin")
            db.add(user_unit)
        else:
            print(f"Updating existing user: {email}")
            user.hashed_password = get_password_hash(password)
            user.is_active = True
            user.estate_id = estate.id
        
        # 3. Add Active Subscription
        sub = (await db.execute(select(Subscription).where(Subscription.user_id == user.id))).scalars().first()
        if not sub:
            sub = Subscription(
                user_id=user.id,
                plan=SubscriptionPlan.PREMIUM,
                status=SubscriptionStatus.ACTIVE,
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=365), # 1 Year
                auto_renew=True
            )
            db.add(sub)
        else:
            sub.plan = SubscriptionPlan.PREMIUM
            sub.status = SubscriptionStatus.ACTIVE
            sub.end_date = datetime.utcnow() + timedelta(days=365)
        
        # 4. Seed a unit access code for review signup.
        signup_access_code = "APPLE123"
        
        # Find user with this code or create placeholder
        code_user = (await db.execute(select(User).where(User.access_code == signup_access_code))).scalars().first()
        if not code_user:
             # Create a valid placeholder user with this code attached to the estate
             code_user = User(
                 email=f"temp_apple_{secrets.token_hex(4)}@gatenode.temp",
                 full_name="New Resident",
                 hashed_password="temp",
                 access_code=signup_access_code,
                 estate_id=estate.id,
                 role=UserRole.RESIDENT
             )
             db.add(code_user)
        
        await db.commit()
        
        print("\n✅ Apple Review Account Ready:")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        print(f"   Subscription: PREMIUM (Active until {sub.end_date.date()})")
        print(f"   Estate: {estate.name}")
        
        print("\n✅ Signup Access Code Generated:")
        print(f"   Code: {signup_access_code}")
        print(f"   (Use this code in the public join flow to attach a resident to a unit)")

if __name__ == "__main__":
    asyncio.run(create_apple_account())
