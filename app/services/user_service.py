import httpx
from typing import Dict, Any
from app.core.config import settings
from app.core.circuit_breaker import user_service_breaker  # <-- Import the breaker
from app.schemas.notification import NotificationType
from fastapi import HTTPException  # Used for internal errors, not to be raised directly

# Shared client instance (defined once for efficiency)
HTTP_CLIENT = httpx.AsyncClient(timeout=5.0)


class UserService:
    def __init__(self):
        self.base_url = settings.USER_SERVICE_URL
        if not self.base_url:
            raise ValueError("User Service URL is not configured.")

    @user_service_breaker  # <-- Apply the Circuit Breaker (R4.1)
    async def get_user_data_and_preferences(self, user_id: str) -> Dict[str, Any]:
        """
        R2.2 & R2.3: Fetches ALL user data (contact info + preferences) in one call.
        This call is wrapped by the Circuit Breaker for resilience (R4.1).

        Returns:
            A dictionary containing user details and preferences.
            Example structure expected from User Service:
            {
                "user_id": "user_42",
                "email": "user@example.com",
                "push_token": "fcm_...",
                "preferences": {"email": true, "push": false}
            }

        Raises:
            httpx.HTTPStatusError: If the downstream service returns 4xx/5xx.
            httpx.RequestError: If connection fails (DNS, timeout, connection reset).
        """
        # Assuming the User Service has a single endpoint for all user data
        url = f"{self.base_url}/api/v1/users/{user_id}/details"

        # Use the shared, persistent client instance
        response = await HTTP_CLIENT.get(url)

        # This will raise httpx.HTTPStatusError for 4xx/5xx statuses
        response.raise_for_status()

        return response.json().get(
            "data", {}
        )  # Assume the response is structured {data: {...}}


# Instantiate service for use in handlers
user_service = UserService()
