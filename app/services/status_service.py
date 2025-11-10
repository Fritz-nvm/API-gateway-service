import redis.asyncio as redis
from typing import Optional, Dict, Any
from datetime import datetime
import json

from app.core.config import settings

# R3.4: Time-To-Live (TTL) for notification status is 24 hours (in seconds)
STATUS_TTL_SECONDS = 86400


class StatusService:
    """Service for tracking notification status using Redis (R3.4)."""

    def __init__(self):
        # Connection will be initialized externally in app/main.py
        self.redis_client: Optional[redis.Redis] = None

    def initialize_client(self):
        """Initializes the Redis client for use by this service."""
        if not self.redis_client:
            self.redis_client = redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                encoding="utf-8",
                decode_responses=True,
            )

    def get_client(self) -> redis.Redis:
        """Returns the initialized Redis client instance."""
        if not self.redis_client:
            raise RuntimeError(
                "Redis client not initialized. Call initialize_client() first."
            )
        return self.redis_client

    async def set_initial_status(self, status_data: Dict[str, Any]) -> bool:
        """
        Stores the initial status (queued) data for a new notification (R3.4).

        Args:
            status_data: A dictionary containing the NotificationResponse fields
                         (notification_id, request_id, status, created_at, etc.).

        Returns:
            True if status was set successfully.
        """
        client = self.get_client()
        notification_id = status_data["notification_id"]
        key = f"notification:status:{notification_id}"

        # Ensure 'updated_at' is present for consistency, even if it's the same as 'created_at'
        if "updated_at" not in status_data:
            status_data["updated_at"] = status_data["created_at"]

        # Convert datetime objects (if any) to ISO format string before JSON dumping
        for k, v in status_data.items():
            if isinstance(v, datetime):
                status_data[k] = v.isoformat()

        # Store status with 24 hour expiry (R3.4)
        await client.setex(key, STATUS_TTL_SECONDS, json.dumps(status_data))

        return True

    async def get_status(self, notification_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve notification status from Redis.

        Returns:
            Status data dict or None if not found
        """
        client = self.get_client()
        key = f"notification:status:{notification_id}"
        status_json = await client.get(key)

        if status_json:
            return json.loads(status_json)

        return None

    async def update_status(
        self, notification_id: str, new_status: str, error_message: Optional[str] = None
    ) -> bool:
        """
        Update existing notification status. This would typically be called by a Worker Service.

        Returns:
            True if status was updated successfully
        """
        client = self.get_client()
        key = f"notification:status:{notification_id}"

        # Retrieve current status and ensure it exists
        status_json = await client.get(key)

        if not status_json:
            return False

        status_data = json.loads(status_json)
        status_data["status"] = new_status
        status_data["updated_at"] = datetime.utcnow().isoformat()

        if error_message:
            status_data["error_message"] = error_message

        # Reset the 24-hour TTL on update
        await client.setex(key, STATUS_TTL_SECONDS, json.dumps(status_data))

        return True


# Create singleton instance
status_service = StatusService()
