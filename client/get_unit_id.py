import asyncio
import sys
import os

sys.path.append(os.getcwd())

from sqlalchemy import select
from core.db import AsyncSessionLocal
from core.models import Unit

async def get_unit_id():
    async with AsyncSessionLocal() as db:
        # Get the unit that has residents (the one we've been using)
        unit = (await db.execute(select(Unit).where(Unit.block_id != None).limit(1))).scalars().first()
        if unit:
            print(f"Unit Number: {unit.unit_number}")
            print(f"Unit ID: {unit.id}")
        else:
            print("No unit found.")

if __name__ == "__main__":
    asyncio.run(get_unit_id())
