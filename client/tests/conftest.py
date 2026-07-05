import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import sys
import os

# Ensure the client directory is in the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest_asyncio.fixture(scope="session")
async def async_client():
    """Provides an async HTTP client matching the iOS app's network layer."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest.fixture(scope="session")
def test_state():
    """Dictionary to share state (like JWT tokens, user IDs) between test suites."""
    return {}
