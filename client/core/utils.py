
import re
from typing import Optional, Dict

def normalize_phone_number(phone: str) -> str:
    """
    Normalize phone number to 080... format.
    """
    # Remove spaces/dashes
    clean = re.sub(r'[^0-9]', '', phone)
    
    # Handle Country Code
    if clean.startswith('234'):
        clean = '0' + clean[3:]
    elif len(clean) == 10 and clean.startswith('0') is False: # 803...
        clean = '0' + clean
        
    return clean

def get_network_from_phone(phone: str) -> Optional[str]:
    """
    Determine Nigerian Network Provider from Phone Number.
    Returns: mtn, airtel, glo, 9mobile, or None.
    """
    phone = normalize_phone_number(phone)
    
    if len(phone) != 11:
        return None
        
    # Prefixes (First 4 digits)
    prefix = phone[:4]
    
    networks = {
        "mtn": [
            "0803", "0806", "0703", "0706", "0813", "0816", "0810", "0814", 
            "0903", "0906", "0913", "0916", "0702", "0704" # Visafone migrated
        ],
        "glo": [
            "0805", "0807", "0705", "0815", "0811", "0905", "0915"
        ],
        "airtel": [
            "0802", "0808", "0708", "0812", "0701", "0902", "0901", "0904", "0907", "0912"
        ],
        "9mobile": [
            "0809", "0818", "0817", "0909", "0908"
        ]
    }
    
    for net, prefixes in networks.items():
        if prefix in prefixes:
            return net
            
    return None

def get_rent_extension_days(estate_home_config: dict) -> int:
    """
    Parses an Estate's home_config to determine how many days 1 billing cycle holds.
    Defaults to 365 (Yearly) if not specified or malformed.
    Expected frequency strings: 'monthly', 'biannually', 'yearly'.
    """
    if not estate_home_config:
        return 365
        
    freq = estate_home_config.get("frequency", "yearly").lower()
    
    if freq == "monthly":
        return 30
    elif freq == "biannually" or freq == "bi-annually":
        return 182 # Approximating half a year
    elif freq == "quarterly":
        return 91
    elif freq == "weekly":
        return 7
    return 365 # Default yearly
