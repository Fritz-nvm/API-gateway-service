from fastapi import APIRouter, status
from app.schemas.response import APIResponse
from datetime import datetime

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Health check endpoint for monitoring and load balancers.
    Returns the service status and basic information.
    """
    health_data = {
        "status": "healthy",
        "service": "API Gateway Service",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
    }

    return APIResponse(success=True, message="Service is running", data=health_data)


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check():
    """
    Readiness check endpoint.
    Returns 200 if the service is ready to accept traffic.
    """
    return {"ready": True, "timestamp": datetime.utcnow().isoformat()}


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_check():
    """
    Liveness check endpoint.
    Returns 200 if the service is alive (not deadlocked).
    """
    return {"alive": True, "timestamp": datetime.utcnow().isoformat()}
