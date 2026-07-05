import pytest
import uuid
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def create_user_and_unit(db):
    from core.models import User, Estate, Block, Unit, UserUnit, HouseholdRole, generate_access_code
    from sqlalchemy.future import select
    from core.security import get_password_hash
    import uuid
    
    estate = (await db.execute(select(Estate).limit(1))).scalars().first()
    if not estate:
        return None, None
        
    block = (await db.execute(select(Block).where(Block.estate_id == estate.id).limit(1))).scalars().first()
    if not block:
        return None, None
        
    unit = (await db.execute(select(Unit).where(Unit.block_id == block.id).limit(1))).scalars().first()
    if not unit:
        return None, None
        
    user = User(
        email=f"houseadmin_{uuid.uuid4().hex[:6]}@example.com",
        first_name="Household",
        last_name="Admin",
        full_name="Household Admin",
        hashed_password=get_password_hash("pass"),
        estate_id=estate.id,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    link = UserUnit(
        user_id=user.id,
        unit_id=unit.id,
        is_primary=True,
        role=HouseholdRole.ADMIN
    )
    db.add(link)
    
    # Session Tracking
    token_id = str(uuid.uuid4())
    user.active_token_id = token_id
    db.add(user)
    await db.commit()
    
    from core.security import create_access_token
    token = create_access_token(subject=user.id, token_id=token_id)
    
    return user, unit, token

async def test_api_add_household_member(async_client: AsyncClient):
    from core.db import AsyncSessionLocal
    from core.models import User
    from sqlalchemy.future import select
    
    async with AsyncSessionLocal() as db:
        user, unit, token = await create_user_and_unit(db)
        if not user:
            pytest.skip("No Estate/Unit available to test.")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": user.estate_id,
        "X-Unit-ID": unit.id
    }
    
    payload = {
        "email": f"NEWMEMBER_{uuid.uuid4().hex[:6]}@EXAMPLE.COM",
        "first_name": "New",
        "last_name": "Kid",
        "role": "resident" 
    }
    
    # 1. Add Member
    response = await async_client.post("/household", json=payload, headers=headers)
    assert response.status_code == 200, f"Failed to add household member: {response.text}"
    
    data = response.json()
    assert "Member added" in data["message"]

    normalized_email = payload["email"].lower()
    async with AsyncSessionLocal() as db:
        created_user = (await db.execute(select(User).where(User.email == normalized_email))).scalars().first()

    assert created_user is not None
    assert created_user.email == normalized_email
    
    # 2. List Members
    list_resp = await async_client.get("/household", headers=headers)
    assert list_resp.status_code == 200
    
    members = list_resp.json()
    assert len(members) >= 2 # The inviter and the invitee
    
    emails = [m["email"] for m in members]
    assert normalized_email in emails
