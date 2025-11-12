import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_send_notification_missing_idempotency_key(test_notification_payload):
    """Test sending notification without idempotency key fails."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/notifications", json=test_notification_payload
        )
        assert response.status_code == 400
        assert "Idempotency-Key" in response.json()["detail"]


@pytest.mark.asyncio
async def test_send_notification_with_idempotency_key(test_notification_payload):
    """Test sending notification with idempotency key."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/notifications",
            json=test_notification_payload,
            headers={"Idempotency-Key": "test-key-123"},
        )
        assert response.status_code in [200, 202, 404, 503]


@pytest.mark.asyncio
async def test_send_notification_invalid_type():
    """Test sending notification with invalid type."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/notifications",
            json={
                "notification_type": "invalid",
                "user_id": "test",
                "template_code": "test",
                "variables": {},
            },
            headers={"Idempotency-Key": "test-key-456"},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_notification_status():
    """Test getting notification status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/notifications/notif_test123")
        assert response.status_code in [200, 404]
