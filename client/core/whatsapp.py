
import httpx
from core.config import settings

def _format_whatsapp_error(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
    except ValueError:
        return response.text

    message = error.get("message") or response.text
    code = error.get("code")
    subcode = error.get("error_subcode")

    if response.status_code == 401 and code == 190 and subcode == 463:
        return (
            f"Meta access token expired. {message} "
            "Update WHATSAPP_API_TOKEN and restart the client service."
        )

    details = []
    if code is not None:
        details.append(f"code={code}")
    if subcode is not None:
        details.append(f"subcode={subcode}")
    details.append(message)
    return " | ".join(details)

async def send_whatsapp_template(to_phone: str, template_name: str, language_code: str = "en_US", components: list = None):
    """
    Send a WhatsApp Template message using Meta Graph API.
    """
    if not settings.WHATSAPP_API_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        print("WARNING: WhatsApp settings not configured. Skipping message.")
        return False
        
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Format phone: Ensure no '+' and just digits. 
    # If starting with '0', remove it and add '234' (assuming Nigeria by default or adapt).
    # Meta requires full international format without '+'.
    clean_phone = to_phone.replace("+", "").replace(" ", "").strip()
    if clean_phone.startswith("0") and len(clean_phone) == 11:
         clean_phone = "234" + clean_phone[1:]
    
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
                "code": language_code
            }
        }
    }
    
    if components:
        payload["template"]["components"] = components
        
    async with httpx.AsyncClient() as client:
        try:
            print(f"DEBUG: Sending WhatsApp template '{template_name}' to {clean_phone}")
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            
            if response.status_code in [200, 201]:
                print(f"DEBUG: WhatsApp sent successfully: {response.json()}")
                return True
            else:
                print(f"ERROR: WhatsApp send failed: {response.status_code} - {_format_whatsapp_error(response)}")
                return False
        except Exception as e:
            print(f"ERROR: Exception sending WhatsApp: {e}")
            return False

async def send_whatsapp_location(to_phone: str, latitude: float, longitude: float, name: str = None, address: str = None):
    """
    Send a WhatsApp Location message.
    NOTE: This may require a business-initiated conversation window to be open unless using a specific template.
    However, if we are responding or if it's allowed, this is the payload.
    """
    if not settings.WHATSAPP_API_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        print("WARNING: WhatsApp settings not configured. Skipping message.")
        return False
        
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    clean_phone = to_phone.replace("+", "").replace(" ", "").strip()
    if clean_phone.startswith("0") and len(clean_phone) == 11:
         clean_phone = "234" + clean_phone[1:]
         
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_phone,
        "type": "location",
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "name": name or "Destination",
            "address": address or ""
        }
    }
    
    async with httpx.AsyncClient() as client:
        try:
            print(f"DEBUG: Sending WhatsApp location to {clean_phone}")
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            
            if response.status_code in [200, 201]:
                 print(f"DEBUG: WhatsApp location sent: {response.json()}")
                 return True
            else:
                 print(f"ERROR: WhatsApp location failed: {response.status_code} - {_format_whatsapp_error(response)}")
                 return False
        except Exception as e:
             print(f"ERROR: Exception sending WhatsApp Location: {e}")
             return False
