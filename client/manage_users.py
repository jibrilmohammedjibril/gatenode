
import asyncio
import sys
import os

# Ensure client directory is in path
sys.path.append(os.path.join(os.path.dirname(__file__), "."))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from core.models import User, Subscription, SubscriptionStatus, SubscriptionPlan, Estate
from core.config import settings
from core.security import get_password_hash
from datetime import datetime, timedelta

# Setup DB
engine = create_async_engine(settings.async_database_url)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def manage_users():
    async with AsyncSessionLocal() as db:
        print("--- Resident Client User Management ---")

        # 1. Activate chinochinedu@hotmail.com
        target_email = "chinochinedu@hotmail.com"
        print(f"\nSearching for {target_email}...")
        
        stmt = select(User).where(User.email == target_email)
        result = await db.execute(stmt)
        user = result.scalars().first()
        
        if user:
            print(f"User found: {user.full_name} ({user.id})")
            
            # Check Subscription
            stmt_sub = select(Subscription).where(Subscription.user_id == user.id)
            res_sub = await db.execute(stmt_sub)
            sub = res_sub.scalars().first()
            
            if not sub:
                print("No subscription found. Creating NEW Active Subscription...")
                sub = Subscription(
                    user_id=user.id,
                    plan=SubscriptionPlan.PREMIUM,
                    status=SubscriptionStatus.ACTIVE,
                    start_date=datetime.utcnow(),
                    end_date=datetime.utcnow() + timedelta(days=365),
                    auto_renew=True
                )
                db.add(sub)
            else:
                print(f"Subscription found. Status: {sub.status}. Updating to ACTIVE...")
                sub.status = SubscriptionStatus.ACTIVE
                sub.plan = SubscriptionPlan.PREMIUM
                sub.end_date = datetime.utcnow() + timedelta(days=365)
            
            await db.commit()
            print(f"✅ {target_email} is now ACTIVE (Premium).")
            
            # Keep estate_id for new user linkage if needed
            estate_id = user.estate_id
        else:
            print(f"❌ User {target_email} NOT FOUND!")
            estate_id = None
        
        # 2. Create Sudo User with Nigerian Name
        print("\nCreating Sudo User...")
        sudo_email = "emeka.okafor@sudo.gatenode.com"
        sudo_name = "Emeka Okafor"
        sudo_pass = "SudoPass123!"
        
        # Check if exists
        stmt = select(User).where(User.email == sudo_email)
        result = await db.execute(stmt)
        sudo_user = result.scalars().first()
        
        if sudo_user:
             print(f"User {sudo_email} already exists. Updating subscription...")
        else:
            print(f"Creating new user {sudo_name}...")
            # Use estate_id from Chino if available, else find first estate or generic
            if not estate_id:
                est_res = await db.execute(select(Estate))
                est = est_res.scalars().first()
                estate_id = est.id if est else None
                
            sudo_user = User(
                email=sudo_email,
                full_name=sudo_name,
                hashed_password=get_password_hash(sudo_pass),
                role="resident",
                is_active=True,
                estate_id=estate_id,
                phone_number="08012345678"
            )
            db.add(sudo_user)
            await db.commit()
            await db.refresh(sudo_user)
            print(f"User Created: {sudo_user.id}")

        # Ensure Sudo Sub
        stmt_sub = select(Subscription).where(Subscription.user_id == sudo_user.id)
        res_sub = await db.execute(stmt_sub)
        sudo_sub = res_sub.scalars().first()
        
        if not sudo_sub:
            sudo_sub = Subscription(
                user_id=sudo_user.id,
                plan=SubscriptionPlan.PREMIUM,
                status=SubscriptionStatus.ACTIVE,
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=365),
                auto_renew=True
            )
            db.add(sudo_sub)
        else:
            sudo_sub.status = SubscriptionStatus.ACTIVE
            sudo_sub.end_date = datetime.utcnow() + timedelta(days=365)
            
        await db.commit()
        print(f"✅ Sudo User {sudo_email} is Active.")
        print(f"Credentials:\n Email: {sudo_email}\n Password: {sudo_pass}")

if __name__ == "__main__":
    asyncio.run(manage_users())
