import asyncio
import os
import sys

# Add client folder to path so 'core' can be imported
sys.path.append(os.path.join(os.getcwd(), "client"))

from core.db import AsyncSessionLocal
from core.models import User, Unit
from sqlalchemy import select

async def get_data():
    async with AsyncSessionLocal() as db:
        # Get a user with a unit
        stmt = select(User).limit(1)
        result = await db.execute(stmt)
        user = result.scalars().first()
        
        if not user:
            print("No user found")
            return

        stmt_unit = select(Unit).limit(1)
        result_unit = await db.execute(stmt_unit)
        unit = result_unit.scalars().first()
        
        print(f"USER_ID={user.id}")
        print(f"UNIT_ID={unit.id if unit else 'None'}")

if __name__ == "__main__":
    asyncio.run(get_data())
