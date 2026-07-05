from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from core.db import get_db, AsyncSessionLocal
from core.models import User, Alert, AlertStatus, UserRole, UserUnit
from core.deps import get_current_user, get_current_unit, require_estate_membership
from core.events import event_manager
from core.notifications import notifications
from datetime import datetime, timezone

router = APIRouter(tags=["Community"])

async def dispatch_alert_notifications(
    alert_id: str,
    user_id: str,
    estate_id: str,
    unit_id: str,
    full_name: str,
    unit_number: str = None
):
    """
    Background task to handle SSE, push, and inbox notifications for a triggered alert.
    """
    async with AsyncSessionLocal() as db:
        print(f"BACKGROUND: Dispatching notifications for alert {alert_id}")
        # 1. SSE Payload
        payload = {
            "alert_id": alert_id,
            "unit_id": str(unit_id) if unit_id else None,
            "triggered_by": str(user_id),
            "location": {"lat": 0.0, "lng": 0.0}, # Mock location
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # 2. Notify self
        print("BACKGROUND: Notifying self...")
        await event_manager.publish("alert:triggered", payload, user_id)
        await notifications.send_emergency_alert(
            db,
            user_id,
            "Alert Triggered",
            "An emergency alert has been triggered.",
            alert_id,
        )
        
        # 3. Notify all Security Guards in the estate
        stmt_guards = select(User).where(
            User.estate_id == estate_id,
            User.role == UserRole.SECURITY
        )
        guards = (await db.execute(stmt_guards)).scalars().all()
        print(f"BACKGROUND: Notifying {len(guards)} guards...")
        
        for guard in guards:
            await event_manager.publish("alert:triggered", payload, guard.id)
            await notifications.send_emergency_alert(
                db=db,
                user_id=guard.id,
                title="🚨 EMERGENCY ALERT",
                body=f"Panic button triggered by {full_name}",
                alert_id=alert_id,
            )

        # 4. Notify Estate Admins
        stmt_admins = select(User).where(
            User.estate_id == estate_id,
            User.role == UserRole.ADMIN
        )
        admins = (await db.execute(stmt_admins)).scalars().all()
        print(f"BACKGROUND: Notifying {len(admins)} admins...")
        
        unit_str = f" at Unit {unit_number}" if unit_number else ""
        for admin in admins:
            await event_manager.publish("alert:triggered", payload, admin.id)
            await notifications.send_emergency_alert(
                db=db,
                user_id=admin.id,
                title="🚨 ESTATE EMERGENCY",
                body=f"Panic button triggered by {full_name}{unit_str}",
                alert_id=alert_id,
            )

        # 5. Notify Household Members
        if unit_id:
            stmt_household = select(User).join(UserUnit, User.id == UserUnit.user_id).where(
                UserUnit.unit_id == unit_id,
                User.id != user_id,
                User.role != UserRole.ADMIN
            )
            household_members = (await db.execute(stmt_household)).scalars().all()
            print(f"BACKGROUND: Notifying {len(household_members)} household members...")
            
            for member in household_members:
                await event_manager.publish("alert:triggered", payload, member.id)
                await notifications.send_emergency_alert(
                    db=db,
                    user_id=member.id,
                    title="🚨 HOUSEHOLD EMERGENCY",
                    body=f"Panic button triggered by {full_name} in your household!",
                    alert_id=alert_id,
                )
        print("BACKGROUND: Dispatch completed.")

@router.post("/alerts/")
async def trigger_emergency(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_estate_membership()),
    unit = Depends(get_current_unit),
    db: AsyncSession = Depends(get_db)
):
    """Panic button. Notifies security immediately."""
    
    alert = Alert(
        type="security", # Default panic
        description="Panic Button Triggered",
        status=AlertStatus.ACTIVE,
        user_id=current_user.id,
        estate_id=current_user.estate_id,
        unit_id=unit.id if unit else None
    )
    
    db.add(alert)
    await db.commit()
    # Removed refresh - ID is already available as it's client-side generated or pre-populated by SA

    await event_manager.notify_channel(
        "security_sse_events",
        {
            "estate_id": current_user.estate_id,
            "data": {
                "type": "alert",
                "alert_id": alert.id,
                "desc": alert.description,
                "severity": "high",
                "status": alert.status.value if hasattr(alert.status, "value") else str(alert.status),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "triggered_by": current_user.id,
                "unit_id": alert.unit_id,
            },
        },
    )

    await event_manager.notify_channel(
        "admin_sse_events",
        {
            "estate_id": current_user.estate_id,
            "event": "alert:triggered",
            "data": {
                "type": "alert",
                "alert_id": alert.id,
                "desc": alert.description,
                "severity": "high",
                "status": alert.status.value if hasattr(alert.status, "value") else str(alert.status),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "triggered_by": current_user.id,
                "triggered_by_name": current_user.full_name,
                "unit_id": alert.unit_id,
                "unit_number": unit.unit_number if unit else None,
            },
        },
    )
    
    # Offload notifications to background
    background_tasks.add_task(
        dispatch_alert_notifications,
        alert_id=alert.id,
        user_id=current_user.id,
        estate_id=current_user.estate_id,
        unit_id=alert.unit_id,
        full_name=current_user.full_name,
        unit_number=unit.unit_number if unit else None
    )
    
    return {"status": "triggered", "message": "Security, Admins, and Household are being notified"}

@router.get("/community/spending")
async def get_community_spending(
    current_user: User = Depends(require_estate_membership())
):
    """Breakdown of estate expenses (Transparency feature)."""
    # Mock data for now until Expense/Budget models exist
    return {
        "month": "October 2023",
        "total_collected": 5000000,
        "total_spent": 3500000,
        "breakdown": [
            {"category": "Diesel/Power", "amount": 2000000, "percentage": 57},
            {"category": "Security", "amount": 1000000, "percentage": 28},
            {"category": "Cleaning", "amount": 500000, "percentage": 14},
        ]
    }
