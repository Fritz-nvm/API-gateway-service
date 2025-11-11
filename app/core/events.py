import logging
import aio_pika

from app.core.config import settings
from app.services.status_service import status_service
from app.schemas.notification import NotificationType

logger = logging.getLogger(__name__)

# Global RabbitMQ state
RABBITMQ_CONNECTION = None
RABBITMQ_CHANNEL = None
NOTIFICATION_EXCHANGE = None


async def startup_handler():
    """Initialize external connections on startup."""
    global RABBITMQ_CONNECTION, RABBITMQ_CHANNEL, NOTIFICATION_EXCHANGE

    logger.info(f"🚀 Starting {settings.PROJECT_NAME} ({settings.ENVIRONMENT})...")

    # Initialize Redis
    try:
        status_service.initialize_client()
        await status_service.get_client().ping()
        logger.info("✅ Redis connected")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")

    # Initialize RabbitMQ
    try:
        RABBITMQ_CONNECTION = await aio_pika.connect_robust(
            settings.QUEUE_URL, timeout=30, reconnect_interval=5
        )
        RABBITMQ_CHANNEL = await RABBITMQ_CONNECTION.channel()

        # Setup Dead Letter Exchange
        dl_exchange = await RABBITMQ_CHANNEL.declare_exchange(
            settings.DEAD_LETTER_EXCHANGE_NAME,
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )
        failed_queue = await RABBITMQ_CHANNEL.declare_queue(
            settings.FAILED_QUEUE_NAME, durable=True
        )
        await failed_queue.bind(dl_exchange, routing_key=settings.FAILED_QUEUE_NAME)

        # Setup Main Exchange and Queues
        NOTIFICATION_EXCHANGE = await RABBITMQ_CHANNEL.declare_exchange(
            "notifications.direct", aio_pika.ExchangeType.DIRECT, durable=True
        )

        dlq_args = {
            "x-dead-letter-exchange": settings.DEAD_LETTER_EXCHANGE_NAME,
            "x-dead-letter-routing-key": settings.FAILED_QUEUE_NAME,
        }

        # Email Queue
        email_queue = await RABBITMQ_CHANNEL.declare_queue(
            settings.EMAIL_QUEUE_NAME, durable=True, arguments=dlq_args
        )
        await email_queue.bind(
            NOTIFICATION_EXCHANGE, routing_key=NotificationType.EMAIL.value
        )

        # Push Queue
        push_queue = await RABBITMQ_CHANNEL.declare_queue(
            settings.PUSH_QUEUE_NAME, durable=True, arguments=dlq_args
        )
        await push_queue.bind(
            NOTIFICATION_EXCHANGE, routing_key=NotificationType.PUSH.value
        )

        logger.info("✅ RabbitMQ connected and queues configured")

    except Exception as e:
        logger.error(f"❌ RabbitMQ setup failed: {e}")


async def shutdown_handler():
    """Close external connections on shutdown."""
    global RABBITMQ_CONNECTION

    logger.info("🔄 Shutting down...")

    if RABBITMQ_CONNECTION:
        await RABBITMQ_CONNECTION.close()
        logger.info("✅ RabbitMQ closed")

    try:
        redis_client = status_service.get_client()
        if redis_client:
            await redis_client.close()
        logger.info("✅ Redis closed")
    except Exception as e:
        logger.error(f"⚠️ Redis close error: {e}")


def get_exchange():
    """Get the notification exchange instance."""
    return NOTIFICATION_EXCHANGE
