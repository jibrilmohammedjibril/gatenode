import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

from sqlalchemy.future import select
from core.db import AsyncSessionLocal
from core.db import AsyncSessionLocal
from core.models import User

async def top_up_user(email: str, amount_naira: int):
    async with AsyncSessionLocal() as db:
        # 1. Find User
        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        user = result.scalars().first()
        
        if not user:
            print(f"❌ User not found: {email}")
            return

        # 2. Credit User Wallet (Personal)
        amount_kobo = amount_naira * 100
        old_balance = user.wallet_balance
        user.wallet_balance += amount_kobo
        
        # 3. Log History (Optional: User has no wallet history table yet, or maybe Transaction?)
        # For now, just save user.
        db.add(user)
        await db.commit()
        
        print(f"✅ Successfully credited {amount_naira} NGN to {email} (User Personal Wallet).")
        print(f"   Old Balance: {old_balance/100:.2f}")
        print(f"   New Balance: {user.wallet_balance/100:.2f}")

if __name__ == "__main__":
    asyncio.run(top_up_user("chinochinedu@gmail.com", 10000))
