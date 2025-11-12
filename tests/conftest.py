import pytest
import asyncio
from typing import AsyncGenerator


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_notification_payload():
    """Sample notification payload for testing."""
    return {
        "notification_type": "email",
        "user_id": "test-user-123",
        "template_code": "welcome_email",
        "variables": {"name": "Test User", "link": "https://example.com"},
        "priority": 5,
        "metadata": {"source": "test"},
    }
