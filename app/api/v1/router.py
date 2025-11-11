from fastapi import APIRouter
from app.api.v1.endpoints.notifications import router as notifications_router

# This is the main router for API version v1 (e.g., /api/v1/...)
# This variable name, api_router, resolves the ImportError.
api_router = APIRouter()

# Include the notifications endpoints
api_router.include_router(
    notifications_router,
    prefix="",  # The endpoints already start with /notifications in their definition
    tags=["notifications"],
)

# Future: If we had a users endpoint (e.g., app.api.v1.endpoints.users),
# we would include it here as well.
# Example: api_router.include_router(users_router, prefix="/users", tags=["users"])
