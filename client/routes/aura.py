from fastapi import APIRouter, Depends
from schemas import AuraRequest, AuraResponse
from core.models import User
from core.deps import get_current_user

router = APIRouter(prefix="/aura", tags=["Aura AI"])

@router.post("/interact", response_model=AuraResponse)
async def aura_interact(
    data: AuraRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Mock AI interaction endpoint.
    In production, this would call an LLM service.
    """
    
    # Simple keyword matching for mock demo
    prompt = data.content.lower()
    
    intent = "unknown"
    response_text = "I'm not sure I understand."
    action = "none"
    params = {}
    
    if "visitor" in prompt or "invite" in prompt:
        intent = "create_invite"
        response_text = "I can help you create a visitor invite. Who is coming?"
        action = "fill_form"
        params = {"form": "invite"}
        
    elif "balance" in prompt or "wallet" in prompt:
        intent = "check_balance"
        response_text = "Checking your wallet balance..."
        action = "navigate"
        params = {"screen": "wallet"}
        
    elif "emergency" in prompt or "help" in prompt:
        intent = "emergency"
        response_text = "Are you in danger? I can trigger the alarm."
        action = "confirm_action"
        params = {"action": "trigger_emergency"}
        
    return {
        "intent": intent,
        "parameters": params,
        "response_text": response_text,
        "action_required": action
    }
