import json
import logging
import aio_pika
from datetime import datetime

from app.schemas.notification import (
    NotificationRequest,
    QueueMessagePayload,
    Meta,
    Priority,
)
from app.core.events import get_exchange

logger = logging.getLogger(__name__)


async def publish_notification(
    payload: NotificationRequest,
    notification_id: str,
    request_id: str,
    correlation_id: str,
):
    """
    Publish notification message to RabbitMQ queue.

    Args:
        payload: Notification request data (from client)
        notification_id: Unique notification identifier (generated)
        request_id: Request ID (from idempotency key)
        correlation_id: Correlation ID for distributed tracing (generated)

    Raises:
        RuntimeError: If RabbitMQ exchange is not initialized
    """
    exchange = get_exchange()
    if not exchange:
        raise RuntimeError("RabbitMQ Exchange is not initialized.")

    # Ensure meta is set
    meta = payload.meta or Meta(priority=Priority.NORMAL, timestamp=datetime.utcnow())
    if meta.timestamp is None:
        meta.timestamp = datetime.utcnow()

    # Create queue message with all required fields
    queue_message = QueueMessagePayload(
        request_id=request_id,
        correlation_id=correlation_id,
        notification_id=notification_id,
        notification_type=payload.notification_type,
        template_id=payload.template_id,
        recipient=payload.recipient,
        variables=payload.variables,
        meta=meta,
        template_validated=False,
        user_preferences_checked=False,
        queued_at=datetime.utcnow(),
    )

    message = aio_pika.Message(
        body=queue_message.model_dump_json().encode(),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        correlation_id=correlation_id,
        message_id=notification_id,
    )

    routing_key = payload.notification_type.value

    await exchange.publish(message, routing_key=routing_key)

    logger.info(f"📤 Published message {notification_id} to '{routing_key}' queue")
