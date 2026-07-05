from fastapi import APIRouter

from schemas import SubscriptionStatusResponse

router = APIRouter(prefix="/subscription", tags=["Subscription"])

@router.get("", response_model=SubscriptionStatusResponse)
async def get_subscription_status():
    """
    App is currently 100% free for all users. 
    Always return active status with infinite days.
    """
    return {
        "status": "active",
        "amount": 0,
        "daysRemaining": 360
    }
