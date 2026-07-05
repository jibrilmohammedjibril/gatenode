"""
APNs Live Activity (Dynamic Island) push notifications.

This module provides functions to send APNs push notifications specifically for
Live Activities (ActivityKit) on iOS 16.2+. These notifications update the Dynamic
Island when the app is backgrounded or closed.
"""
from typing import Optional
import time
from core.apns import get_apns_token
import httpx

APNS_PRODUCTION_URL = "https://api.push.apple.com/3/device"
APNS_SANDBOX_URL = "https://api.sandbox.push.apple.com/3/device"

async def send_live_activity_update(
    activity_push_token: str,
    title: str,
    subtitle: str,
    timer_end_date_ms: Optional[int] = None,
    progress: Optional[float] = None,
    use_sandbox: bool = False
):
    """
    Send an 'update' event to a Live Activity.
    
    Args:
        activity_push_token: The ActivityKit push token (hex/base64)
        title: Primary text (e.g., visitor name)
        subtitle: Status text (e.g., "Checked In")
        timer_end_date_ms: Optional countdown timer (epoch milliseconds)
        progress: Optional progress bar (0.0 to 1.0)
        use_sandbox: Use sandbox APNs endpoint
        
    Returns:
        bool: True if successful, False otherwise
    """
    apns_url = APNS_SANDBOX_URL if use_sandbox else APNS_PRODUCTION_URL
    url = f"{apns_url}/{activity_push_token}"
    
    # Get APNs JWT token
    apns_jwt = get_apns_token()
    
    # Build content-state matching expo-live-activity schema
    content_state = {
        "title": title,
        "subtitle": subtitle,
        "timerEndDateInMilliseconds": timer_end_date_ms,
        "progress": progress,
        "imageName": None,
        "dynamicIslandImageName": None
    }
    
    # Build APNs payload
    payload = {
        "aps": {
            "timestamp": int(time.time()),
            "event": "update",
            "content-state": content_state
        }
    }
    
    headers = {
        "apns-push-type": "liveactivity",
        "apns-topic": "com.gatenode.resident.push-type.liveactivity",
        "apns-priority": "10",
        "authorization": f"bearer {apns_jwt}",
        "content-type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        
        if response.status_code != 200:
            print(f"❌ Live Activity update failed: {response.status_code} - {response.text}")
        else:
            print(f"✅ Live Activity updated: {title} - {subtitle}")
    
    return response.status_code == 200

async def send_live_activity_end(
    activity_push_token: str,
    title: str,
    subtitle: str,
    use_sandbox: bool = False
):
    """
    Send an 'end' event to terminate a Live Activity.
    
    Args:
        activity_push_token: The ActivityKit push token (hex/base64)
        title: Primary text (e.g., visitor name)
        subtitle: Final status text (e.g., "Checked out")
        use_sandbox: Use sandbox APNs endpoint
        
    Returns:
        bool: True if successful, False otherwise
    """
    apns_url = APNS_SANDBOX_URL if use_sandbox else APNS_PRODUCTION_URL
    url = f"{apns_url}/{activity_push_token}"
    
    apns_jwt = get_apns_token()
    
    content_state = {
        "title": title,
        "subtitle": subtitle,
        "timerEndDateInMilliseconds": None,
        "progress": None,
        "imageName": None,
        "dynamicIslandImageName": None
    }
    
    payload = {
        "aps": {
            "timestamp": int(time.time()),
            "event": "end",
            "content-state": content_state
        }
    }
    
    headers = {
        "apns-push-type": "liveactivity",
        "apns-topic": "com.gatenode.resident.push-type.liveactivity",
        "apns-priority": "10",
        "authorization": f"bearer {apns_jwt}",
        "content-type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        
        if response.status_code != 200:
            print(f"❌ Live Activity end failed: {response.status_code} - {response.text}")
        else:
            print(f"✅ Live Activity ended: {title}")
    
    return response.status_code == 200
