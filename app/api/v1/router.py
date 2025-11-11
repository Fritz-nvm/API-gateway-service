from fastapi import APIRouter
from app.api.v1.endpoints.notifications import router as notifications_router
from app.api.v1.endpoints import health, notifications


# This is the main router for API version v1 (e.g., /api/v1/...)
# This variable name, api_router, resolves the ImportError.
api_router = APIRouter()

# Include the notifications endpoints
api_router.include_router(
    notifications_router,
    prefix="",  # The endpoints already start with /notifications in their definition
    tags=["notifications"],
)

# Include health endpoints (no prefix, so /api/v1/health works)
api_router.include_router(health.router, tags=["Health"])
