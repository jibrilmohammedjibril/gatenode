import asyncio
import json
import ssl
import logging
from typing import Dict, List, Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import asyncpg
from core.config import settings

logger = logging.getLogger(__name__)


def _event_db_connect_config() -> tuple[str, ssl.SSLContext | bool | None]:
    raw_url = settings.async_database_url
    if raw_url.startswith("postgresql+asyncpg://"):
        raw_url = raw_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    elif raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql://", 1)

    parsed = urlparse(raw_url)
    ssl_value = None
    kept_query: list[tuple[str, str]] = []

    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key in {"ssl", "sslmode"} and ssl_value is None:
            ssl_value = value.strip().lower()
            continue
        kept_query.append((key, value))

    ssl_context: ssl.SSLContext | bool | None = None
    if ssl_value in {"disable", "false", "0", "off"}:
        ssl_context = False
    elif ssl_value in {"require", "verify-ca", "verify-full", "true", "1", "on"}:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ssl_context = ctx

    clean_url = urlunparse(parsed._replace(query=urlencode(kept_query)))
    return clean_url, ssl_context

class EventManager:
    """
    Postgres-Backed Event Manager for SSE.
    Uses LISTEN/NOTIFY to broadcast events across multiple worker processes.
    """
    def __init__(self):
        self.user_connections: Dict[str, List[asyncio.Queue]] = {}
        self.db_pool = None
        self.listen_task = None

    async def connect(self):
        """Establish DB pool and start listening."""
        if not self.db_pool:
            clean_url, ssl_context = _event_db_connect_config()
            logger.info("Connecting to Event DB. SSL: %s", ssl_context)

            pool_kwargs = {
                "dsn": clean_url,
                "min_size": 0,
                "max_size": 10,
            }
            if ssl_context is not None:
                pool_kwargs["ssl"] = ssl_context

            self.db_pool = await asyncpg.create_pool(**pool_kwargs)
            self.listen_task = asyncio.create_task(self._listen_for_notifications())
            logger.info("EventManager connected to Postgres.")

    async def _listen_for_notifications(self):
        """Continuous listener for Postgres NOTIFY channels."""
        try:
            async with self.db_pool.acquire() as conn:
                logger.info("SSE Listener: Adding listener to 'sse_events' channel.")
                await conn.add_listener("sse_events", self._handle_notification)
                logger.info("SSE Listener: Listener added successfully.")
                while True:
                    await asyncio.sleep(3600) # Keep connection alive
        except Exception as e:
            logger.error(f"SSE Listener Error: {e}", exc_info=True)
            # Retry logic could go here
    
    def _handle_notification(self, connection, pid, channel, payload):
        """Callback when Postgres sends a notification."""
        try:
            logger.info(f"SSE Received Notification: {payload}")
            message = json.loads(payload)
            target_user_id = message.get("user_id")
            event = message.get("event")
            data = message.get("data")
            
            # If broadcast (no user_id) or strictly matching user locally connected
            if target_user_id:
                if target_user_id in self.user_connections:
                    logger.info(f"SSE Dispatching to user {target_user_id}: {event}")
                    self._dispatch_local(target_user_id, event, data)
                else:
                    logger.debug(f"SSE User {target_user_id} not connected locally.")
            else:
                # Broadcast to all local
                logger.info(f"SSE Broadcasting to all: {event}")
                for uid in self.user_connections:
                    self._dispatch_local(uid, event, data)
                    
        except Exception as e:
            logger.error(f"Error handling SSE notification: {e}", exc_info=True)

    def _dispatch_local(self, user_id: str, event: str, data: Any):
        """Dispatch to local asyncio queues for a user."""
        if user_id in self.user_connections:
            msg = {"event": event, "data": data}
            for q in self.user_connections[user_id]:
                asyncio.create_task(q.put(msg))

    async def subscribe(self, user_id: str) -> asyncio.Queue:
        if not self.db_pool:
            await self.connect()
            
        queue = asyncio.Queue()
        if user_id not in self.user_connections:
            self.user_connections[user_id] = []
        self.user_connections[user_id].append(queue)
        logger.info(f"User {user_id} subscribed to SSE.")
        return queue

    async def unsubscribe(self, user_id: str, queue: asyncio.Queue):
        if user_id in self.user_connections:
            if queue in self.user_connections[user_id]:
                self.user_connections[user_id].remove(queue)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        logger.info(f"User {user_id} unsubscribed from SSE.")

    async def publish(self, event_type: str, data: Dict[str, Any], user_id: str = None):
        """
        Publish event via Postgres NOTIFY.
        This distributes it to ALL workers.
        """
        if not self.db_pool:
            await self.connect()
            
        payload = {
            "user_id": user_id,
            "event": event_type,
            "data": data
        }
        try:
            async with self.db_pool.acquire() as conn:
                # Use pg_notify to avoid SQL injection and handle complex payloads
                await conn.execute("SELECT pg_notify('sse_events', $1)", json.dumps(payload))
                logger.info(f"SSE Event Published: {event_type} for User: {user_id}")
        except Exception as e:
            logger.error(f"Failed to publish event: {e}", exc_info=True)

    async def notify_channel(self, channel: str, payload: Dict[str, Any]):
        """
        Publish raw payload to an arbitrary Postgres NOTIFY channel.
        Used for cross-service realtime events.
        """
        if not self.db_pool:
            await self.connect()

        async with self.db_pool.acquire() as conn:
            await conn.execute("SELECT pg_notify($1, $2)", channel, json.dumps(payload))

    async def disconnect(self):
        """Close DB pool."""
        if self.db_pool:
            await self.db_pool.close()
            logger.info("EventManager disconnected from Postgres.")

# Global Instance
event_manager = EventManager()
