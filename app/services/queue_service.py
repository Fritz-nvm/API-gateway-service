import json
import logging
import aio_pika

from app.schemas.notification import NotificationRequest
from app.core.events import get_exchange

logger = logging.getLogger(__name__)


async def publish_notification(
    payload: NotificationRequest, notification_id: str, idempotency_key: str
):
    """
    Publish notification message to RabbitMQ queue.

    Args:
        payload: Notification request data
        notification_id: Unique notification identifier
        idempotency_key: Idempotency key for duplicate detection

    Raises:
        RuntimeError: If RabbitMQ exchange is not initialized
    """
    exchange = get_exchange()
    if not exchange:
        raise RuntimeError("RabbitMQ Exchange is not initialized.")

    message_payload = {
        "notification_type": payload.notification_type.value,
        "template_id": payload.template_id,
        "recipient": payload.recipient.model_dump(exclude_none=True),
        "variables": payload.variables,
        "notification_id": notification_id,
        "idempotency_key": idempotency_key,
    }

    message = aio_pika.Message(
        body=json.dumps(message_payload).encode(),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        correlation_id=idempotency_key,
        message_id=notification_id,
    )

    routing_key = payload.notification_type.value

    await exchange.publish(message, routing_key=routing_key)

    logger.info(f"📤 Published message {notification_id} to '{routing_key}' queue")
