from fastapi import FastAPI
from app.core.config import settings
from app.services.queue_service import queue_service

# REMOVED: from app.services.redis_service import redis_service
from app.services.idempotency_service import idempotency_service
from app.services.status_service import status_service

# Import routers
from app.api.v1.router import api_router


def create_app() -> FastAPI:
    """Initializes and returns the FastAPI application."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        debug=settings.DEBUG,
    )

    app.include_router(api_router, prefix="/api/v1")

    @app.on_event("startup")
    async def startup_event():
        """Connects to external services on application startup."""
        print(f"Starting API Gateway Service (Env: {settings.ENVIRONMENT})...")

        # 1. Initialize Redis clients first
        try:
            # Initialize the clients for the services that require Redis
            idempotency_service.initialize_client()
            status_service.initialize_client()

            # Test Redis Connection (R4.2, R3.1) using the Idempotency Service client
            await idempotency_service.get_client().ping()
            print("INFO: Redis connection established for all services.")
        except Exception:
            print(
                "CRITICAL: Failed to connect to Redis. Idempotency and Status services are disabled."
            )

        # 2. Connect to RabbitMQ (R3.3)
        try:
            await queue_service.connect()
            print("INFO: RabbitMQ connection established and queues declared.")
        except HTTPException as e:
            # Catch the HTTPException (503) raised by queue_service.connect()
            print(f"CRITICAL: Failed to connect to Message Queue: {e.detail}")
        except Exception:
            # Catch other potential exceptions
            print("WARNING: Could not connect to Message Queue. Check RabbitMQ status.")

    @app.on_event("shutdown")
    async def shutdown_event():
        """Gracefully closes connections on application shutdown."""
        # 1. Close RabbitMQ
        await queue_service.close()

        # 2. Close Redis connections
        if idempotency_service.redis_client:
            await idempotency_service.redis_client.close()
        if status_service.redis_client:
            await status_service.redis_client.close()

    return app


app = create_app()
