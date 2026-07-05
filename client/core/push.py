import firebase_admin
from firebase_admin import credentials, messaging
from typing import Dict, Any, List
import json
import logging
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete

from core.config import settings
from core.config import settings
from core.models import DeviceToken, User
from core.apns import get_apns_client

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
_firebase_app = None

def get_firebase_app():
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app
        
    if not settings.FIREBASE_CREDENTIALS:
        logger.warning("FIREBASE_CREDENTIALS not set. Push notifications will be disabled.")
        return None
        
    try:
        cred_dict = json.loads(settings.FIREBASE_CREDENTIALS)
        cred = credentials.Certificate(cred_dict)
        _firebase_app = firebase_admin.initialize_app(cred)
        return _firebase_app
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
        return None

async def send_push_notification(
    token: str, 
    title: str, 
    body: str, 
    data: Dict[str, Any] = None, 
    db: AsyncSession = None,
    platform: str = "android",
    # Advanced Options
    channel_id: str = "default",
    group: str = None,
    ttl: int = None, # Seconds
    silent: bool = False,
    collapse_key: str = None
):
    """
    Send a single push notification via Firebase FCM with advanced configs.
    """
    if not token:
        return

    # 1. Route strictly by explicitly registered Platform
    if platform.lower() == "ios":
        # Check if the token is actually an FCM token (FCM tokens usually contain a colon, while APNs device tokens are hex strings)
        if ":" not in token:
            try:
                 apns = get_apns_client()
                 result = await apns.send_notification(token, title, body, data)
                 if result == "Unregistered" and db:
                      # Handle cleanup if unregistered
                      await db.execute(delete(DeviceToken).where(DeviceToken.token == token))
                      await db.commit()
                 return
            except Exception as e:
                 logger.error(f"Failed to send Direct APNs Notification: {e}")
                 return

    app = get_firebase_app()
    if not app:
        return

    # FCM expects data values to be strings
    fcm_data = {k: str(v) for k, v in (data or {}).items()}
    
    # Android Config
    android_config = messaging.AndroidConfig(
        priority="high",
        ttl=ttl, # Expiry
        collapse_key=collapse_key,
        notification=messaging.AndroidNotification(
            channel_id=channel_id,
            tag=group # Grouping
        ) if not silent else None,
        data=fcm_data if silent else None 
        # Note: data is usually top-level, but for silent sync sometimes needed in config
    )
    
    # APNs Config (iOS)
    apns_headers = {}
    if ttl:
        import time
        expiration = int(time.time()) + ttl
        apns_headers["apns-expiration"] = str(expiration)
    if collapse_key:
        apns_headers["apns-collapse-id"] = collapse_key

    aps = messaging.Aps(
        content_available=True if silent else False, # For background sync
        sound="default" if not silent else None,
        thread_id=group
    )
    
    apns_config = messaging.APNSConfig(
        headers=apns_headers,
        payload=messaging.APNSPayload(
            aps=aps
        )
    )
    
    # Construct Message
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ) if not silent else None,
        data=fcm_data,
        token=token,
        android=android_config,
        apns=apns_config
    )
    
    try:
        response = messaging.send(message)
        logger.info(f"Successfully sent FCM message: {response}")
    except messaging.UnregisteredError:
        logger.warning(f"FCM token unregistered: {token}. Removing from database.")
        if db:
            try:
                await db.execute(delete(DeviceToken).where(DeviceToken.token == token))
                await db.commit()
            except Exception as db_err:
                logger.error(f"Failed to remove unregistered token from DB: {db_err}")
    except Exception as e:
        logger.error(f"Failed to send FCM push to {token}: {e}")

async def notify_user_devices(user_id: str, title: str, body: str, data: Dict[str, Any], db: AsyncSession, **kwargs):
    """
    Send push to all registered devices for a user.
    """
    # Filter: Only send to devices that match the User's Active Session
    stmt = (
        select(DeviceToken)
        .join(User, DeviceToken.user_id == User.id)
        .where(
            DeviceToken.user_id == user_id,
            User.settings_push_enabled == True,
            DeviceToken.active_token_id == User.active_token_id,
        )
    )
    result = await db.execute(stmt)
    tokens = result.scalars().all()

    if not tokens:
        logger.warning("No active device tokens registered for client push target user=%s", user_id)
        return
    
    for dt in tokens:
        await send_push_notification(dt.token, title, body, data, db, platform=dt.platform or "android", **kwargs)
