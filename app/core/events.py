import logging
import aio_pika
import asyncio
from urllib.parse import urlparse

from app.core.config import settings
from app.services.status_service import status_service
from app.schemas.notification import NotificationType

logger = logging.getLogger(__name__)

# Global RabbitMQ state
_RABBITMQ_CONNECTION = None
_RABBITMQ_CHANNEL = None
_NOTIFICATION_EXCHANGE = None


async def _wait_for_tcp(
    host: str, port: int, timeout: float = 1.0, retries: int = 30
) -> bool:
    """Wait for a TCP port to become available."""
    for _ in range(retries):
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            await asyncio.sleep(timeout)
    return False


async def startup_handler():
    """Initialize external connections on startup."""
    global _RABBITMQ_CONNECTION, _RABBITMQ_CHANNEL, _NOTIFICATION_EXCHANGE

    logger.info(f"🚀 Starting {settings.PROJECT_NAME} ({settings.ENVIRONMENT})...")

    # Initialize Redis
    try:
        init_result = status_service.initialize_client()
        if asyncio.iscoroutine(init_result):
            await init_result
        ping_result = status_service.get_client().ping()
        if asyncio.iscoroutine(ping_result):
            await ping_result
        logger.info("✅ Redis connected")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        raise  # Fail startup if Redis unavailable

    # Parse RabbitMQ host/port and wait for TCP before attempting AMQP connect
    try:
        parsed = urlparse(settings.QUEUE_URL)
        rabbit_host = parsed.hostname or "rabbitmq"
        rabbit_port = int(parsed.port or 5672)
    except Exception:
        rabbit_host, rabbit_port = "rabbitmq", 5672

    logger.info(
        f"⏳ Waiting for RabbitMQ TCP {rabbit_host}:{rabbit_port} to be available..."
    )
    await _wait_for_tcp(rabbit_host, rabbit_port, timeout=1.0, retries=30)

    # Initialize RabbitMQ with retry logic
    max_retries = 5
    retry_delay = 5

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                f"🔄 Connecting to RabbitMQ (attempt {attempt}/{max_retries})..."
            )
            logger.info(f"📡 RabbitMQ URL: {settings.QUEUE_URL}")

            _RABBITMQ_CONNECTION = await aio_pika.connect_robust(
                settings.QUEUE_URL, timeout=30, reconnect_interval=5
            )
            _RABBITMQ_CHANNEL = await _RABBITMQ_CONNECTION.channel()
            logger.info("✅ RabbitMQ connection established")

            # Setup Dead Letter Exchange
            dl_exchange = await _RABBITMQ_CHANNEL.declare_exchange(
                settings.DEAD_LETTER_EXCHANGE_NAME,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )
            logger.info(
                f"✅ Dead Letter Exchange declared: {settings.DEAD_LETTER_EXCHANGE_NAME}"
            )

            failed_queue = await _RABBITMQ_CHANNEL.declare_queue(
                settings.FAILED_QUEUE_NAME, durable=True
            )
            await failed_queue.bind(dl_exchange, routing_key=settings.FAILED_QUEUE_NAME)
            logger.info(f"✅ Failed queue configured: {settings.FAILED_QUEUE_NAME}")

            # Setup Main Exchange and Queues
            _NOTIFICATION_EXCHANGE = await _RABBITMQ_CHANNEL.declare_exchange(
                "notifications.direct", aio_pika.ExchangeType.DIRECT, durable=True
            )
            logger.info("✅ Main notification exchange declared: notifications.direct")

            dlq_args = {
                "x-dead-letter-exchange": settings.DEAD_LETTER_EXCHANGE_NAME,
                "x-dead-letter-routing-key": settings.FAILED_QUEUE_NAME,
            }

            # Email Queue
            email_queue = await _RABBITMQ_CHANNEL.declare_queue(
                settings.EMAIL_QUEUE_NAME, durable=True, arguments=dlq_args
            )
            await email_queue.bind(
                _NOTIFICATION_EXCHANGE, routing_key=NotificationType.EMAIL.value
            )
            logger.info(f"✅ Email queue configured: {settings.EMAIL_QUEUE_NAME}")

            # Push Queue
            push_queue = await _RABBITMQ_CHANNEL.declare_queue(
                settings.PUSH_QUEUE_NAME, durable=True, arguments=dlq_args
            )
            await push_queue.bind(
                _NOTIFICATION_EXCHANGE, routing_key=NotificationType.PUSH.value
            )
            logger.info(f"✅ Push queue configured: {settings.PUSH_QUEUE_NAME}")

            logger.info("✅ RabbitMQ fully configured and ready!")
            break  # Success - exit retry loop

        except Exception as e:
            logger.error(f"❌ RabbitMQ connection attempt {attempt} failed: {e}")
            logger.exception(e)  # Print full stack trace

            if attempt < max_retries:
                logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(
                    "❌ Failed to connect to RabbitMQ after all retry attempts!"
                )
                raise RuntimeError(f"RabbitMQ initialization failed: {e}")


async def shutdown_handler():
    """Close external connections on shutdown."""
    global _RABBITMQ_CONNECTION

    logger.info("🔄 Shutting down...")

    if _RABBITMQ_CONNECTION and not _RABBITMQ_CONNECTION.is_closed:
        try:
            await _RABBITMQ_CONNECTION.close()
            logger.info("✅ RabbitMQ connection closed")
        except Exception as e:
            logger.error(f"⚠️ Error closing RabbitMQ: {e}")

    try:
        close_result = status_service.close()
        if asyncio.iscoroutine(close_result):
            await close_result
        logger.info("✅ Redis connection closed")
    except Exception as e:
        logger.error(f"⚠️ Redis close error: {e}")


def get_exchange():
    """Get the notification exchange instance."""
    if not _NOTIFICATION_EXCHANGE:
        logger.error("❌ Exchange requested but not initialized!")
    return _NOTIFICATION_EXCHANGE


def is_rabbitmq_ready() -> bool:
    """Check if RabbitMQ connection is ready."""
    global _RABBITMQ_CONNECTION, _NOTIFICATION_EXCHANGE
    return (
        _NOTIFICATION_EXCHANGE is not None
        and _RABBITMQ_CONNECTION is not None
        and not _RABBITMQ_CONNECTION.is_closed
    )
