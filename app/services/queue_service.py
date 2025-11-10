import aio_pika
import json
from typing import Optional
from fastapi import HTTPException, status

from app.core.config import settings
from app.schemas.notification import QueueMessagePayload, NotificationType


class QueueService:
    """Service for publishing messages to RabbitMQ (R3.3)."""

    def __init__(self):
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None

    async def connect(self):
        """Initialize RabbitMQ connection and channel."""
        if not self.connection or self.connection.is_closed:
            try:
                self.connection = await aio_pika.connect_robust(
                    f"amqp://{settings.QUEUE_USERNAME}:{settings.QUEUE_PASSWORD}@"
                    f"{settings.QUEUE_HOST}:{settings.QUEUE_PORT}/"
                )
                self.channel = await self.connection.channel()

                # Declare queues for both email and push workers
                await self.channel.declare_queue(
                    settings.EMAIL_QUEUE_NAME, durable=True
                )
                await self.channel.declare_queue(settings.PUSH_QUEUE_NAME, durable=True)

            except Exception as e:
                # Raise HTTPException (503 Service Unavailable) on connection failure
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Failed to connect to message queue: {str(e)}",
                )

    async def close(self):
        """Close RabbitMQ connection."""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()

    async def publish_notification(self, payload: QueueMessagePayload) -> bool:
        """
        Publish notification to appropriate queue based on notification type.

        Returns:
            True if message was published successfully
        """
        # Ensure connection is established (useful if called outside of main app flow,
        # but typically handled during startup)
        if not self.channel or self.channel.is_closed:
            await self.connect()

        # Determine which queue to use (R3.3 routing)
        queue_name = (
            settings.EMAIL_QUEUE_NAME
            if payload.notification_type == NotificationType.EMAIL
            else settings.PUSH_QUEUE_NAME
        )

        try:
            # Convert payload to JSON
            message_body = payload.model_dump_json()

            # Create message (R3.3 persistence and priority)
            message = aio_pika.Message(
                body=message_body.encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,  # Make message persistent
                priority=self._get_priority(payload.meta.priority),
                correlation_id=payload.correlation_id,
                message_id=payload.notification_id,
            )

            # Publish to queue via the default exchange
            await self.channel.default_exchange.publish(message, routing_key=queue_name)

            return True

        except Exception as e:
            # Raise HTTPException (500 Internal Server Error) on publish failure
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to publish message to queue '{queue_name}': {str(e)}",
            )

    def _get_priority(self, priority_str: str) -> int:
        """Convert priority string to integer (0-9 for RabbitMQ)."""
        priority_map = {"low": 3, "normal": 5, "high": 9}
        return priority_map.get(priority_str, 5)


# Create singleton instance
queue_service = QueueService()
