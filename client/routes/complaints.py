from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.db import get_db
from core.models import Complaint, ComplaintCategory, ComplaintPriority, User
from core.deps import require_estate_membership
from schemas import ComplaintCreate, ComplaintResponse

router = APIRouter(prefix="/complaints", tags=["Complaints"])

@router.post("", response_model=ComplaintResponse)
async def submit_complaint(
    data: ComplaintCreate,
    current_user: User = Depends(require_estate_membership()), # Sets RLS
    db: AsyncSession = Depends(get_db)
):
    # Payload has unitId optional.
    # If provided, use it. If not, maybe use default?
    # Spec says "unitId: uuid (optional)"
    
    unit_id = data.unitId
    if not unit_id:
        # Try to infer? Or leave null? 
        # Models allows unit_id nullable? line 140 models.py: unit_id nullable=True.
        # But usually a complaint is about a unit or estate?
        # Let's verify unitId belongs to user if provided?
        pass

    try:
        category_enum = ComplaintCategory(data.category.lower())
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid category: {data.category}. Valid options: {[e.value for e in ComplaintCategory]}"
        )
        
    try:
        priority_enum = ComplaintPriority(data.priority.lower())
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid priority: {data.priority}. Valid options: {[e.value for e in ComplaintPriority]}"
        )

    new_complaint = Complaint(
        category=category_enum,
        priority=priority_enum,
        description=data.description,
        user_id=current_user.id,
        estate_id=current_user.estate_id,
        unit_id=unit_id,
        attachments=data.attachments
    )
    
    db.add(new_complaint)
    await db.commit()
    await db.refresh(new_complaint)
    
    return {
        "id": new_complaint.id,
        "ticketNumber": new_complaint.ticket_number,
        "category": new_complaint.category,
        "priority": new_complaint.priority,
        "description": new_complaint.description,
        "status": new_complaint.status,
        "createdAt": str(new_complaint.created_at),
        "attachments": new_complaint.attachments
    }


@router.get("", response_model=list[ComplaintResponse])
async def list_complaints(
    page: int = 1,
    limit: int = 20,
    current_user: User = Depends(require_estate_membership()),
    db: AsyncSession = Depends(get_db)
):
    query = select(Complaint).where(Complaint.user_id == current_user.id)
    query = query.order_by(Complaint.created_at.desc())
    query = query.offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(query)
    complaints = result.scalars().all()
    
    return [
        {
            "id": c.id,
            "ticketNumber": c.ticket_number,
            "category": c.category,
            "priority": c.priority,
            "description": c.description,
            "status": c.status,
            "createdAt": str(c.created_at),
            "attachments": c.attachments or []
        }
        for c in complaints
    ]
