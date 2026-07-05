import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.future import select

pytestmark = pytest.mark.asyncio


async def _create_authenticated_resident():
    from core.db import AsyncSessionLocal
    from core.models import Block, Estate, Unit, User, UserUnit
    from core.security import create_access_token, get_password_hash

    async with AsyncSessionLocal() as db:
        estate = Estate(
            name=f"Incident Estate {uuid.uuid4().hex[:6]}",
            address="1 Safety Avenue",
        )
        db.add(estate)
        await db.flush()

        block = Block(name="Block A", estate_id=estate.id)
        db.add(block)
        await db.flush()

        unit = Unit(block_id=block.id, unit_number=f"Flat {uuid.uuid4().hex[:4].upper()}")
        db.add(unit)
        await db.flush()

        user = User(
            email=f"incident_{uuid.uuid4().hex[:8]}@example.com",
            first_name="Incident",
            last_name="Reporter",
            full_name="Incident Reporter",
            hashed_password=get_password_hash("pass"),
            estate_id=estate.id,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        db.add(
            UserUnit(
                user_id=user.id,
                unit_id=unit.id,
                is_primary=True,
            )
        )

        token_id = str(uuid.uuid4())
        user.active_token_id = token_id
        await db.commit()

    token = create_access_token(subject=user.id, token_id=token_id)
    return user, unit, token


async def test_report_incident_creates_security_complaint(async_client: AsyncClient):
    from core.db import AsyncSessionLocal
    from core.models import Incident, IncidentCategory, IncidentPriority

    user, unit, token = await _create_authenticated_resident()

    payload = {
        "title": " Suspicious movement near gate ",
        "location": " Gate B ",
        "description": " Someone was seen trying to access the estate. ",
        "category": "security",
        "priority": "high",
        "attachments": ["https://files.example.com/incidents/photo-1.jpg"],
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Estate-ID": user.estate_id,
        "X-Tenant-ID": user.estate_id,
        "X-Unit-ID": unit.id,
        "X-Platform": "ios",
    }

    response = await async_client.post("/incidents", json=payload, headers=headers)
    assert response.status_code == 200, response.text

    data = response.json()
    assert data["title"] == "Suspicious movement near gate"
    assert data["location"] == "Gate B"
    assert data["description"] == "Someone was seen trying to access the estate."
    assert data["category"] == "security"
    assert data["priority"] == "high"
    assert data["status"] == "pending"
    assert data["attachments"] == payload["attachments"]
    assert data["ticketNumber"].startswith("INC-")

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Incident).where(Incident.id == data["id"]))
        incident = result.scalars().first()

    assert incident is not None
    assert incident.user_id == user.id
    assert incident.unit_id == unit.id
    assert incident.category == IncidentCategory.SECURITY
    assert incident.priority == IncidentPriority.HIGH
    assert incident.attachments == payload["attachments"]
    assert incident.title == "Suspicious movement near gate"
    assert incident.location == "Gate B"
    assert incident.description == "Someone was seen trying to access the estate."


async def test_report_incident_rejects_blank_required_fields(async_client: AsyncClient):
    user, unit, token = await _create_authenticated_resident()

    payload = {
        "title": "   ",
        "location": "Gate B",
        "description": "Saw suspicious activity",
        "category": "security",
        "attachments": [],
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Estate-ID": user.estate_id,
        "X-Tenant-ID": user.estate_id,
        "X-Unit-ID": unit.id,
    }

    response = await async_client.post("/incidents", json=payload, headers=headers)
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "title is required"


async def test_report_incident_rejects_invalid_category(async_client: AsyncClient):
    user, unit, token = await _create_authenticated_resident()

    payload = {
        "title": "Suspicious movement",
        "location": "Gate B",
        "description": "Saw suspicious activity",
        "category": "other",
        "attachments": [],
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Estate-ID": user.estate_id,
        "X-Tenant-ID": user.estate_id,
        "X-Unit-ID": unit.id,
    }

    response = await async_client.post("/incidents", json=payload, headers=headers)
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Invalid category. Only 'security' is supported"
