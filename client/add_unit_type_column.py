import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

from sqlalchemy import text
from core.db import engine

async def add_column():
    async with engine.begin() as conn:
        print("Checking if column unit_type exists in 'estates' table...")
        try:
            # Check if column exists
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='estates' AND column_name='unit_type'"
            ))
            if result.scalar():
                print("Column 'unit_type' already exists.")
            else:
                print("Adding column 'unit_type'...")
                await conn.execute(text("ALTER TABLE estates ADD COLUMN unit_type VARCHAR DEFAULT 'Unit'"))
                print("Column added successfully.")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(add_column())
