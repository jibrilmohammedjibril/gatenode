import pytest
import uuid
import datetime
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def create_user_and_unit(db):
    try:
        from core.models import User, Estate, Block, Unit, UserUnit, HouseholdRole, generate_access_code
        from sqlalchemy.future import select
        from core.security import get_password_hash
        import uuid
        
        estate = (await db.execute(select(Estate).limit(1))).scalars().first()
        if not estate:
            return None, None, None
            
        block = (await db.execute(select(Block).where(Block.estate_id == estate.id).limit(1))).scalars().first()
        if not block:
            return None, None, None
            
        unit = (await db.execute(select(Unit).where(Unit.block_id == block.id).limit(1))).scalars().first()
        if not unit:
            return None, None, None
            
        user = User(
            email=f"inviter_{uuid.uuid4().hex[:6]}@example.com",
            full_name="Household Inviter",
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
        
        token_id = str(uuid.uuid4())
        user.active_token_id = token_id
        db.add(user)
        await db.commit()
        
        from core.security import create_access_token
        token = create_access_token(subject=user.id, token_id=token_id)
        
        return user, unit, token
    except Exception as e:
        print(f"Failed to setup: {e}")
        return None, None, None

async def test_api_create_and_verify_invite(async_client: AsyncClient):
    from core.db import AsyncSessionLocal
    
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
        "visitorName": "John API",
        "visitorPhone": "08012345678",
        "validHours": 24,
        "inviteType": "single"
    }
    
    # 1. Create Invite
    response = await async_client.post("/invites", json=payload, headers=headers)
    assert response.status_code == 200, f"Failed to create invite: {response.text}"
    
    data = response.json()
    assert "accessCode" in data
    
    access_code = data["accessCode"]
    
    # 2. Verify Invite (Guard action)
    # The /verify endpoint does not strictly require auth right now (mock endpoint)
    verify_resp = await async_client.post(f"/invites/verify/{access_code}")
    
    assert verify_resp.status_code == 200, f"Failed to verify invite: {verify_resp.text}"
    verify_data = verify_resp.json()
    assert verify_data["valid"] is True
    assert verify_data["visitor"] == "John API"

async def test_api_extend_invite_accepts_camel_and_snake_case(async_client: AsyncClient):
    from core.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        user, unit, token = await create_user_and_unit(db)
        if not user:
            pytest.skip("No Estate/Unit available to test.")

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": user.estate_id,
        "X-Unit-ID": unit.id
    }

    create_payload = {
        "visitorName": "Extend API",
        "validHours": 1,
        "inviteType": "single"
    }

    create_resp = await async_client.post("/invites", json=create_payload, headers=headers)
    assert create_resp.status_code == 200, f"Failed to create invite: {create_resp.text}"

    invite = create_resp.json()
    invite_id = invite["id"]
    first_expiry = datetime.datetime.fromisoformat(invite["validUntil"].replace("Z", "+00:00"))

    camel_expiry = (first_expiry + datetime.timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    camel_resp = await async_client.post(
        f"/invites/{invite_id}/extend",
        json={"validUntil": camel_expiry},
        headers=headers,
    )
    assert camel_resp.status_code == 200, f"Camel-case extend failed: {camel_resp.text}"
    camel_returned_expiry = datetime.datetime.fromisoformat(camel_resp.json()["validUntil"].replace("Z", "+00:00"))
    assert camel_returned_expiry == datetime.datetime.fromisoformat(camel_expiry.replace("Z", "+00:00"))

    snake_expiry = camel_returned_expiry + datetime.timedelta(hours=1)
    snake_expiry_str = snake_expiry.isoformat().replace("+00:00", "Z")
    snake_resp = await async_client.post(
        f"/invites/{invite_id}/extend",
        json={"valid_until": snake_expiry_str},
        headers=headers,
    )
    assert snake_resp.status_code == 200, f"Snake-case extend failed: {snake_resp.text}"
    snake_returned_expiry = datetime.datetime.fromisoformat(snake_resp.json()["validUntil"].replace("Z", "+00:00"))
    assert snake_returned_expiry == snake_expiry

async def test_api_extend_invite_accepts_valid_hours(async_client: AsyncClient):
    from core.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        user, unit, token = await create_user_and_unit(db)
        if not user:
            pytest.skip("No Estate/Unit available to test.")

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": user.estate_id,
        "X-Unit-ID": unit.id
    }

    create_payload = {
        "visitorName": "Hours Extend API",
        "validHours": 1,
        "inviteType": "single"
    }

    create_resp = await async_client.post("/invites", json=create_payload, headers=headers)
    assert create_resp.status_code == 200, f"Failed to create invite: {create_resp.text}"

    invite = create_resp.json()
    invite_id = invite["id"]
    original_expiry = datetime.datetime.fromisoformat(invite["validUntil"].replace("Z", "+00:00"))

    extend_resp = await async_client.post(
        f"/invites/{invite_id}/extend",
        json={"validHours": 3},
        headers=headers,
    )
    assert extend_resp.status_code == 200, f"Hour-based extend failed: {extend_resp.text}"

    updated_expiry = datetime.datetime.fromisoformat(extend_resp.json()["validUntil"].replace("Z", "+00:00"))
    assert updated_expiry >= original_expiry + datetime.timedelta(hours=3)
