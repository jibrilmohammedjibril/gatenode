
import httpx
from core.config import settings

async def get_fez_delivery_cost(destination_state: str, pickup_state: str = None, weight: float = None) -> dict:
    """
    Fetch delivery cost from Fez Delivery API.
    """
    if not settings.FEZ_DELIVERY_SECRET_KEY:
        print("WARNING: FEZ_DELIVERY_SECRET_KEY is not set.")
        return None

    url = f"{settings.FEZ_DELIVERY_BASE_URL}/order/cost"
    
    headers = {
        "secret-key": settings.FEZ_DELIVERY_SECRET_KEY,
        "bg-bypass-cache": "true", # Optional, sometimes helps with sandbox
        "Content-Type": "application/json"
    }
    
    payload = {
        "state": destination_state
    }
    
    if pickup_state:
        payload["pickUpState"] = pickup_state
        
    if weight:
        payload["weight"] = weight
        
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
            
            if response.status_code == 200:
                data = response.json()
                # Expected format:
                # {
                #   "status": "Success",
                #   "description": "Cost Fetched Successfully",
                #   "Cost": [ { "state": "Kano", "cost": "900" } ]
                # }
                if data.get("status") == "Success" and "Cost" in data:
                    cost_list = data["Cost"]
                    if isinstance(cost_list, list) and len(cost_list) > 0:
                         # Return the first match or just the list? The schema usually returns one item if state is specific.
                         item = cost_list[0]
                         return {
                             "cost": float(item.get("cost", 0)),
                             "state": item.get("state")
                         }
            else:
                print(f"Fez API Error: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"Fez API Exception: {e}")
            
    return None
