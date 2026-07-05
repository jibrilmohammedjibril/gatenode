import asyncio
import time
import jwt
import httpx
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional
from core.config import settings

logger = logging.getLogger(__name__)

class APNsClient:
    def __init__(self):
        self.team_id = settings.APPLE_TEAM_ID
        self.key_id = settings.APPLE_KEY_ID
        self.bundle_id = settings.APPLE_BUNDLE_ID
        self.use_sandbox = settings.APPLE_USE_SANDBOX
        
        env_name = "SANDBOX" if self.use_sandbox else "PRODUCTION"
        logger.info(f"🍏 APNs Client Initialized. Environment: {env_name} ({settings.APPLE_BUNDLE_ID})")
        
        # Load Private Key
        self.private_key = None
        if settings.APPLE_P8_PATH:
            try:
                # If path is a file, read it. If it's the key content itself, use it.
                if settings.APPLE_P8_PATH.startswith("-----BEGIN PRIVATE KEY-----"):
                    self.private_key = settings.APPLE_P8_PATH
                elif " " not in settings.APPLE_P8_PATH and len(settings.APPLE_P8_PATH) > 100:
                    try:
                        import base64
                        decoded = base64.b64decode(settings.APPLE_P8_PATH).decode("utf-8")
                        if "-----BEGIN PRIVATE KEY-----" in decoded:
                            self.private_key = decoded
                        else:
                             # Maybe it's a file path that looks like base64, so fallback to open
                             raise ValueError("Not a PEM key after decode")
                    except Exception:
                        # Fallback to file open
                        with open(settings.APPLE_P8_PATH, "r") as f:
                            self.private_key = f.read()
                else:
                    with open(settings.APPLE_P8_PATH, "r") as f:
                        self.private_key = f.read()
            except Exception as e:
                logger.error(f"Failed to load APNs Private Key: {e}")

        # Endpoint
        self.base_url = "https://api.development.push.apple.com" if self.use_sandbox else "https://api.push.apple.com"
        
        # HTTP Client (Long-lived for reuse)
        self._client = httpx.AsyncClient(http2=True)
        self._token_cache = None
        self._token_expiry = 0

    def get_jwt_token(self) -> str:
        """
        Generates a JWT token for APNs authentication.
        Tokens are valid for up to 1 hour. We cache for 50 mins.
        """
        now = time.time()
        if self._token_cache and now < self._token_expiry:
            return self._token_cache

        if not self.private_key or not self.team_id or not self.key_id:
            logger.error("Missing APNs credentials (Team ID, Key ID, or Private Key)")
            return None

        payload = {
            "iss": self.team_id,
            "iat": int(now)
        }
        headers = {
            "alg": "ES256",
            "kid": self.key_id
        }

        token = jwt.encode(payload, self.private_key, algorithm="ES256", headers=headers)
        
        self._token_cache = token
        self._token_expiry = now + (50 * 60) # Refresh every 50 mins
        return token

    async def send_notification(self, device_token: str, title: str, body: str, data: Dict[str, Any] = None):
        """
        Sends a notification directly to APNs.
        """
        jwt_token = self.get_jwt_token()
        if not jwt_token:
            logger.warning("Cannot send APNs: Authentication failed.")
            return False

        headers = {
            "authorization": f"bearer {jwt_token}",
            "apns-topic": self.bundle_id,
            "apns-push-type": "alert", # 'background' for silent
            "apns-priority": "10" # 10=Immediate, 5=Power/Conserve
        }

        # Construct Payload (APS)
        payload = {
            "aps": {
                "alert": {
                    "title": title,
                    "body": body
                },
                "sound": "default"
            }
        }
        
        # Add custom data (flattened into root)
        if data:
            for k, v in data.items():
                if k != "aps":
                    payload[k] = v

        url = f"{self.base_url}/3/device/{device_token}"
        
        logger.info(f"📤 Sending APNs Payload: {json.dumps(payload)}")

        try:
            response = await self._client.post(url, headers=headers, json=payload, timeout=5.0)
            
            if response.status_code == 200:
                logger.info(f"APNs Send Success: {response.headers.get('apns-id')}")
                return True
            else:
                try:
                    error_json = response.json()
                    reason = error_json.get('reason')
                except:
                    reason = response.text
                
                logger.error(f"APNs Send Failed ({response.status_code}): {reason} [Env: {'SANDBOX' if self.use_sandbox else 'PRODUCTION'}]")
                
                if response.status_code == 410: # Unregistered
                    return "Unregistered"
                    
                return False
                
        except Exception as e:
            logger.error(f"APNs Network Error: {e}")
            return False

    async def close(self):
        await self._client.aclose()

# Global Client Instance
_apns_client = None

def get_apns_client():
    global _apns_client
    if not _apns_client:
        _apns_client = APNsClient()
    return _apns_client
