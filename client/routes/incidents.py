from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.db import get_db
from core.deps import get_current_user, require_estate_membership
from core.models import Incident, IncidentCategory, IncidentPriority, IncidentStatus, User, UserUnit
from schemas import IncidentCreate, IncidentResponse

router = APIRouter(prefix="/incidents", tags=["Incidents"])


def _require_non_empty_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    return cleaned


def _normalize_attachments(attachments: list[str]) -> list[str]:
    normalized: list[str] = []
    for url in attachments:
        cleaned = url.strip()
        if not cleaned:
            raise HTTPException(status_code=400, detail="attachments must not contain empty values")
        if not cleaned.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="attachments must contain uploaded file URLs")
        normalized.append(cleaned)
    return normalized


async def _next_incident_ticket_number(db: AsyncSession) -> str:
    result = await db.execute(text("SELECT nextval('incident_ticket_number_seq')"))
    ticket_sequence = result.scalar_one()
    return f"INC-{ticket_sequence:06d}"


async def require_incident_context(
    x_estate_id: str = Header(..., alias="X-Estate-ID"),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_unit_id: str = Header(..., alias="X-Unit-ID"),
    _x_platform: str | None = Header(None, alias="X-Platform"),
    current_user: User = Depends(require_estate_membership()),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if x_estate_id != current_user.estate_id:
        raise HTTPException(status_code=403, detail="X-Estate-ID does not match the authenticated user's estate")

    if x_tenant_id != current_user.estate_id:
        raise HTTPException(status_code=403, detail="X-Tenant-ID does not match the authenticated user's estate")

    stmt = select(UserUnit).where(
        UserUnit.user_id == current_user.id,
        UserUnit.unit_id == x_unit_id,
    )
    result = await db.execute(stmt)
    user_unit = result.scalars().first()
    if not user_unit:
        raise HTTPException(status_code=403, detail="Access to this unit denied")

    return {
        "current_user": current_user,
        "unit_id": x_unit_id,
    }


@router.post("", response_model=IncidentResponse)
async def create_incident(
    data: IncidentCreate,
    context: dict = Depends(require_incident_context),
    db: AsyncSession = Depends(get_db),
):
    current_user: User = context["current_user"]
    unit_id: str = context["unit_id"]

    title = _require_non_empty_text(data.title, "title")
    location = _require_non_empty_text(data.location, "location")
    description = _require_non_empty_text(data.description, "description")
    attachments = _normalize_attachments(data.attachments)

    if data.category.strip().lower() != IncidentCategory.SECURITY.value:
        raise HTTPException(status_code=400, detail="Invalid category. Only 'security' is supported")

    try:
        priority = IncidentPriority((data.priority or IncidentPriority.HIGH.value).lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority: {data.priority}. Valid options: {[e.value for e in IncidentPriority]}",
        )

    incident = Incident(
        ticket_number=await _next_incident_ticket_number(db),
        title=title,
        location=location,
        description=description,
        category=IncidentCategory.SECURITY,
        priority=priority,
        status=IncidentStatus.PENDING,
        attachments=attachments,
        user_id=current_user.id,
        unit_id=unit_id,
        estate_id=current_user.estate_id,
    )

    db.add(incident)
    await db.commit()
    await db.refresh(incident)

    return {
        "id": incident.id,
        "ticketNumber": incident.ticket_number,
        "status": incident.status,
        "title": incident.title,
        "location": incident.location,
        "description": incident.description,
        "category": incident.category,
        "priority": incident.priority,
        "attachments": incident.attachments or [],
        "createdAt": incident.created_at,
    }
