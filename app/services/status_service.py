import redis.asyncio as redis
from typing import Optional, Dict, Any
from datetime import datetime
import json
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# R3.4: Time-To-Live (TTL) for notification status is 24 hours (in seconds)
STATUS_TTL_SECONDS = 86400
# R3.2: Idempotency key TTL (5 minutes by default)
IDEMPOTENCY_TTL_SECONDS = getattr(settings, "IDEMPOTENCY_WINDOW_SECONDS", 300)


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
            logger.info(
                f"✅ Redis client initialized: {settings.REDIS_HOST}:{settings.REDIS_PORT}"
            )

    def get_client(self) -> redis.Redis:
        """Returns the initialized Redis client instance."""
        if not self.redis_client:
            raise RuntimeError(
                "Redis client not initialized. Call initialize_client() first."
            )
        return self.redis_client

    # --- Idempotency Methods (R3.2) ---

    async def check_idempotency_key(self, idempotency_key: str) -> Optional[str]:
        """
        Check if an idempotency key exists and return the associated notification_id.

        Args:
            idempotency_key: The idempotency key to check

        Returns:
            The notification_id if found, None otherwise
        """
        try:
            client = self.get_client()
            key = f"idempotency:{idempotency_key}"
            notification_id = await client.get(key)

            if notification_id:
                logger.info(
                    f"🔍 Idempotency key found: {idempotency_key} -> {notification_id}"
                )

            return notification_id
        except Exception as e:
            logger.error(f"❌ Error checking idempotency key: {e}")
            return None

    async def set_idempotency_key(
        self, idempotency_key: str, notification_id: str
    ) -> bool:
        """
        Set an idempotency key with associated notification_id.

        Args:
            idempotency_key: The idempotency key
            notification_id: The notification ID to associate

        Returns:
            True if set successfully, False if key already exists
        """
        try:
            client = self.get_client()
            key = f"idempotency:{idempotency_key}"

            # Use SETNX (SET if Not eXists) to prevent race conditions
            result = await client.set(
                key,
                notification_id,
                ex=IDEMPOTENCY_TTL_SECONDS,
                nx=True,  # Only set if key doesn't exist
            )

            if result:
                logger.info(
                    f"🔒 Idempotency key locked: {idempotency_key} -> {notification_id}"
                )
            else:
                logger.warning(f"⚠️ Idempotency key already exists: {idempotency_key}")

            return result
        except Exception as e:
            logger.error(f"❌ Error setting idempotency key: {e}")
            return False

    # --- Status Tracking Methods (R3.4) ---

    async def set_initial_status(self, status_data: Dict[str, Any]) -> bool:
        """
        Stores the initial status (queued) data for a new notification (R3.4).

        Args:
            status_data: A dictionary containing the NotificationResponse fields
                         (notification_id, request_id, status, created_at, etc.).

        Returns:
            True if status was set successfully.
        """
        try:
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

            logger.info(
                f"📊 Initial status set: {notification_id} -> {status_data.get('status')}"
            )
            return True
        except Exception as e:
            logger.error(f"❌ Error setting initial status: {e}")
            return False

    async def get_status(self, notification_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve notification status from Redis.

        Returns:
            Status data dict or None if not found
        """
        try:
            client = self.get_client()
            key = f"notification:status:{notification_id}"
            status_json = await client.get(key)

            if status_json:
                logger.info(f"📊 Status retrieved: {notification_id}")
                return json.loads(status_json)

            logger.warning(f"⚠️ Status not found: {notification_id}")
            return None
        except Exception as e:
            logger.error(f"❌ Error getting status: {e}")
            return None

    async def update_status(
        self, notification_id: str, new_status: str, error_message: Optional[str] = None
    ) -> bool:
        """
        Update existing notification status. This would typically be called by a Worker Service.

        Returns:
            True if status was updated successfully
        """
        try:
            client = self.get_client()
            key = f"notification:status:{notification_id}"

            # Retrieve current status and ensure it exists
            status_json = await client.get(key)

            if not status_json:
                logger.warning(
                    f"⚠️ Cannot update non-existent status: {notification_id}"
                )
                return False

            status_data = json.loads(status_json)
            status_data["status"] = new_status
            status_data["updated_at"] = datetime.utcnow().isoformat()

            if error_message:
                status_data["error_message"] = error_message

            # Reset the 24-hour TTL on update
            await client.setex(key, STATUS_TTL_SECONDS, json.dumps(status_data))

            logger.info(f"📊 Status updated: {notification_id} -> {new_status}")
            return True
        except Exception as e:
            logger.error(f"❌ Error updating status: {e}")
            return False

    # --- Utility Methods ---

    async def delete_status(self, notification_id: str) -> bool:
        """
        Delete notification status from Redis.

        Args:
            notification_id: The notification ID

        Returns:
            True if deleted, False otherwise
        """
        try:
            client = self.get_client()
            key = f"notification:status:{notification_id}"
            result = await client.delete(key)

            if result:
                logger.info(f"🗑️ Status deleted: {notification_id}")

            return bool(result)
        except Exception as e:
            logger.error(f"❌ Error deleting status: {e}")
            return False

    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("✅ Redis connection closed")


# Create singleton instance
status_service = StatusService()
