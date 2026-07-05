
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging

# Configure logging at the entry point
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
from core.tasks import start_scheduler

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from core.rate_limit import limiter
from routes import (
    auth,
    user,
    kyc,
    bills,
    wallet,
    services,
    vehicles,
    incidents,
    invites,
    complaints,
    household,
    notifications,
    community,
    events,
    upload,
    device_tokens,
    subscriptions,
    dashboard,
    config,
    webhooks,
    aura,
    public,
    support,
    live_activities,
    feed,
    dm
)

app = FastAPI(title="Gatenode Resident Client API", version="1.0.0")

# ── Rate Limiter (Redis-backed) ──────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS (Allow from frontend mainly) # Changed comment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # TODO: Restrict in production # Added TODO comment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(kyc.router)
app.include_router(bills.router)
app.include_router(wallet.router)
app.include_router(services.router)
app.include_router(vehicles.router)
app.include_router(incidents.router)
app.include_router(invites.router, prefix="/invites")
app.include_router(live_activities.router, prefix="/live-activities")

app.include_router(complaints.router)
app.include_router(household.router)
app.include_router(notifications.router)
app.include_router(community.router)
app.include_router(events.router)
app.include_router(upload.router)
app.include_router(device_tokens.router)
app.include_router(subscriptions.router)
app.include_router(webhooks.router)
app.include_router(aura.router)
app.include_router(dashboard.router)
app.include_router(public.router)
app.include_router(config.router)
app.include_router(support.router)
app.include_router(feed.router)
app.include_router(dm.router)

@app.get("/")
async def root():
    return {"message": "Welcome to the Resident Client API"}

@app.on_event("startup")
async def run_migrations():
    from core.config import validate_startup_settings
    from core.db import run_startup_migrations

    validate_startup_settings()
    await run_startup_migrations()
    start_scheduler()
    
@app.on_event("shutdown")
async def shutdown_event():
    print("Shutting down Application...")
    await events.event_manager.disconnect()
    from core.db import engine
    await engine.dispose()
    print("DB Connections Closed.")
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "client"}
