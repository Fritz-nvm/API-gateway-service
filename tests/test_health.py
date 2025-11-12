import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_liveness_endpoint():
    """Test liveness endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/live")
        assert response.status_code == 200
        data = response.json()
        assert data["alive"] is True


@pytest.mark.asyncio
async def test_readiness_endpoint():
    """Test readiness endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/ready")
        assert response.status_code in [200, 503]


# @pytest.mark.asyncio
# async def test_health_endpoint():
#     """Test health endpoint returns 200."""
#     transport = ASGITransport(app=app)
#     async with AsyncClient(transport=transport, base_url="http://test") as client:
#         response = await client.get("/api/v1/health")
#         assert response.status_code == 200
#         data = response.json()
#         assert "service" in data
#         assert "status" in data
