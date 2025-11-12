from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from app.schemas.response import APIResponse
from app.core.config import settings
from app.services.status_service import status_service
from app.core.events import is_rabbitmq_ready
from app.core.circuit_breaker import get_all_breakers_status
from datetime import datetime
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Comprehensive health check endpoint for monitoring and load balancers.
    Returns the service status, dependency health, and circuit breaker states.

    Returns:
        - 200: All systems healthy
        - 503: One or more systems degraded/unhealthy
    """
    health_data = {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "redis": {"status": "unknown", "message": ""},
            "rabbitmq": {"status": "unknown", "message": ""},
        },
        "circuit_breakers": {},
    }

    all_healthy = True

    # Check Redis
    try:
        redis_client = status_service.get_client()
        await redis_client.ping()
        health_data["checks"]["redis"] = {
            "status": "healthy",
            "message": "Connected and responsive",
        }
        logger.debug("✅ Redis health check passed")
    except Exception as e:
        all_healthy = False
        health_data["checks"]["redis"] = {
            "status": "unhealthy",
            "message": f"Connection failed: {str(e)}",
        }
        logger.error(f"❌ Redis health check failed: {e}")

    # Check RabbitMQ
    try:
        if is_rabbitmq_ready():
            health_data["checks"]["rabbitmq"] = {
                "status": "healthy",
                "message": "Connected and exchange ready",
            }
            logger.debug("✅ RabbitMQ health check passed")
        else:
            all_healthy = False
            health_data["checks"]["rabbitmq"] = {
                "status": "unhealthy",
                "message": "Exchange not initialized",
            }
            logger.error("❌ RabbitMQ health check failed: Exchange not ready")
    except Exception as e:
        all_healthy = False
        health_data["checks"]["rabbitmq"] = {
            "status": "unhealthy",
            "message": f"Check failed: {str(e)}",
        }
        logger.error(f"❌ RabbitMQ health check failed: {e}")

    # Get circuit breaker status
    try:
        health_data["circuit_breakers"] = get_all_breakers_status()

        # Check if any circuit breaker is OPEN
        for breaker_name, breaker_info in health_data["circuit_breakers"].items():
            if breaker_info["state"] == "open":
                all_healthy = False
                logger.warning(f"⚡ Circuit breaker '{breaker_name}' is OPEN")
    except Exception as e:
        logger.error(f"❌ Failed to get circuit breaker status: {e}")

    # Set overall status
    if not all_healthy:
        health_data["status"] = "degraded"
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=health_data
        )

    return JSONResponse(status_code=status.HTTP_200_OK, content=health_data)


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check():
    """
    Kubernetes readiness probe endpoint.
    Returns 200 if the service is ready to accept traffic.
    Checks that all critical dependencies are available.

    Returns:
        - 200: Service is ready
        - 503: Service is not ready (dependencies unavailable)
    """
    ready = True
    checks = {}

    # Check Redis readiness
    try:
        redis_client = status_service.get_client()
        await redis_client.ping()
        checks["redis"] = "ready"
    except Exception as e:
        ready = False
        checks["redis"] = f"not ready: {str(e)}"
        logger.warning(f"⚠️ Redis not ready: {e}")

    # Check RabbitMQ readiness
    if is_rabbitmq_ready():
        checks["rabbitmq"] = "ready"
    else:
        ready = False
        checks["rabbitmq"] = "not ready: exchange not initialized"
        logger.warning("⚠️ RabbitMQ not ready")

    # Check circuit breakers are not OPEN
    try:
        breakers = get_all_breakers_status()
        open_breakers = [
            name for name, info in breakers.items() if info["state"] == "open"
        ]

        if open_breakers:
            ready = False
            checks["circuit_breakers"] = f"open: {', '.join(open_breakers)}"
        else:
            checks["circuit_breakers"] = "ready"
    except Exception as e:
        logger.error(f"❌ Failed to check circuit breakers: {e}")

    response = {
        "ready": ready,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
    }

    if not ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=response
        )

    return JSONResponse(status_code=status.HTTP_200_OK, content=response)


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_check():
    """
    Kubernetes liveness probe endpoint.
    Returns 200 if the service is alive (not deadlocked or crashed).
    This is a simple check that doesn't depend on external services.

    Returns:
        - 200: Always (unless the service is completely dead)
    """
    return {
        "alive": True,
        "timestamp": datetime.utcnow().isoformat(),
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }


@router.get("/metrics", status_code=status.HTTP_200_OK)
async def metrics():
    """
    Basic metrics endpoint for monitoring.
    Returns current circuit breaker states and dependency status.
    """
    metrics_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "service": settings.PROJECT_NAME,
        "circuit_breakers": get_all_breakers_status(),
        "dependencies": {},
    }

    # Redis metrics
    try:
        redis_client = status_service.get_client()
        info = await redis_client.info()
        metrics_data["dependencies"]["redis"] = {
            "status": "connected",
            "connected_clients": info.get("connected_clients", 0),
            "used_memory_human": info.get("used_memory_human", "unknown"),
            "uptime_in_seconds": info.get("uptime_in_seconds", 0),
        }
    except Exception as e:
        metrics_data["dependencies"]["redis"] = {
            "status": "unavailable",
            "error": str(e),
        }

    # RabbitMQ metrics
    metrics_data["dependencies"]["rabbitmq"] = {
        "status": "connected" if is_rabbitmq_ready() else "unavailable",
        "exchange_ready": is_rabbitmq_ready(),
    }

    return metrics_data
