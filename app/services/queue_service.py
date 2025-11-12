import json
import logging
import aio_pika
from datetime import datetime

from app.schemas.notification import NotificationRequest, QueueMessagePayload
from app.core.events import get_exchange, is_rabbitmq_ready
from app.core.circuit_breaker import async_circuit_breaker, rabbitmq_breaker

logger = logging.getLogger(__name__)


@async_circuit_breaker(rabbitmq_breaker)
async def publish_notification(
    payload: NotificationRequest,
    notification_id: str,
    request_id: str,
    correlation_id: str,
):
    """
    Publish notification message to RabbitMQ queue with circuit breaker protection.
    """
    if not is_rabbitmq_ready():
        logger.error("❌ RabbitMQ not ready - exchange not initialized")
        raise RuntimeError("RabbitMQ Exchange is not initialized.")

    exchange = get_exchange()
    if not exchange:
        raise RuntimeError("RabbitMQ Exchange is not initialized.")

    # Create queue message with new format
    try:
        queue_message = QueueMessagePayload(
            request_id=request_id,
            correlation_id=correlation_id,
            notification_id=notification_id,
            notification_type=payload.notification_type,
            user_id=payload.user_id,
            template_code=payload.template_code,
            variables=payload.variables,
            priority=payload.priority,
            metadata=payload.metadata,
            template_validated=False,
            user_preferences_checked=False,
            queued_at=datetime.utcnow(),
        )
    except Exception as e:
        logger.error(f"❌ Failed to create queue message: {e}")
        raise

    message = aio_pika.Message(
        body=queue_message.model_dump_json().encode(),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        correlation_id=correlation_id,
        message_id=notification_id,
        priority=payload.priority,
    )

    routing_key = payload.notification_type.value

    try:
        await exchange.publish(message, routing_key=routing_key)
        logger.info(
            f"📤 Published message {notification_id} to '{routing_key}' queue",
            extra={
                "correlation_id": correlation_id,
                "notification_id": notification_id,
                "user_id": payload.user_id,
            },
        )
    except Exception as e:
        logger.error(f"❌ Failed to publish to RabbitMQ: {e}")
        raise
