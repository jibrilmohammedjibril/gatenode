"""
Rate Limiting Module — Redis-backed via SlowAPI (Limits library)
Shared across the resident client services.

Usage in routes:
    from core.rate_limit import limiter, RateLimits
    
    @router.post("/login")
    @limiter.limit(RateLimits.AUTH)
    async def login(request: Request, ...):
        ...

Rate tiers defined in RateLimits:
  - AUTH       : Strict — 5/minute  (login, signup, password reset, OTP)
  - SENSITIVE  : Tight  — 10/minute (PIN verify, KYC submission, payments)
  - STANDARD   : Normal — 60/minute (most authenticated endpoints)
  - UPLOAD     : Loose  — 20/minute (file/image uploads)
  - WEBHOOK    : Open   — 300/minute (payment webhooks — high-volume)
  - PUBLIC     : Open   — 30/minute (public unauth endpoints like invite verify)
"""
import os
from slowapi import Limiter
from slowapi.util import get_remote_address

# Redis URL from environment (injectable per service)
REDIS_URL = os.environ.get("REDIS_URL", "redis://default:zuche8g3n2fvpvgx@107.155.122.87:6379")

limiter = Limiter(
    key_func=get_remote_address,   # Rate-limit per IP address
    storage_uri=REDIS_URL,
    default_limits=["200/minute"],  # Global fallback limit
)

class RateLimits:
    """Centralised rate limit strings. Use with @limiter.limit(...)"""
    
    # Auth & Onboarding — very strict to prevent brute force
    AUTH = "5/minute"
    
    # OTP / Sensitive actions — prevent abuse
    SENSITIVE = "10/minute"
    
    # Standard authenticated API calls
    STANDARD = "60/minute"

    # File upload endpoints
    UPLOAD = "20/minute"

    # Webhook endpoints — called by payment providers at volume
    WEBHOOK = "300/minute"

    # Public / unauthenticated endpoints
    PUBLIC = "30/minute"
