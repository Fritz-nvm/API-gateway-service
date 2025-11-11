import asyncio
import uuid
import logging
import json

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

import aio_pika

# Local Imports
from app.core.config import settings
from app.schemas.notification import SendNotificationRequest, NotificationType
from app.services.status_service import status_service

# --- 1. App Initialization ---

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- 2. Global State ---
# Store RabbitMQ connection and channel globally
RABBITMQ_CONNECTION = None
RABBITMQ_CHANNEL = None
NOTIFICATION_EXCHANGE = None


# --- 3. Startup and Shutdown Events ---


@app.on_event("startup")
async def startup_event():
    """Initializes external connections: Redis and RabbitMQ."""
    global RABBITMQ_CONNECTION, RABBITMQ_CHANNEL, NOTIFICATION_EXCHANGE

    # R4.2: Initialize and test Redis connection
    try:
        status_service.initialize_client()
        await status_service.get_client().ping()
        logging.info("Redis connection established for Status Service.")
    except Exception as e:
        logging.error(
            f"CRITICAL: Failed to connect to Redis. Idempotency and status tracking disabled. Error: {e}"
        )
        # Note: In a production system, this would be a hard failure.

    # R3.3: Initialize RabbitMQ connection and setup queues
    try:
        RABBITMQ_CONNECTION = await aio_pika.connect_robust(settings.QUEUE_URL)
        RABBITMQ_CHANNEL = await RABBITMQ_CONNECTION.channel()

        # --- DEAD LETTER QUEUE (DLQ) SETUP (R3.5) ---

        # 1. Declare the Dead Letter Exchange (DLE)
        dl_exchange = await RABBITMQ_CHANNEL.declare_exchange(
            settings.DEAD_LETTER_EXCHANGE_NAME,
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )

        # 2. Declare the Failed Queue (DLQ)
        failed_queue = await RABBITMQ_CHANNEL.declare_queue(
            settings.FAILED_QUEUE_NAME, durable=True
        )

        # 3. Bind the Failed Queue to the DLE
        await failed_queue.bind(dl_exchange, routing_key=settings.FAILED_QUEUE_NAME)
        logging.info(
            f"Dead Letter Queue '{settings.FAILED_QUEUE_NAME}' and DLE setup complete."
        )

        # --- PRIMARY EXCHANGE/QUEUE SETUP ---

        # Declare the main direct exchange
        NOTIFICATION_EXCHANGE = await RABBITMQ_CHANNEL.declare_exchange(
            "notifications.direct", aio_pika.ExchangeType.DIRECT, durable=True
        )

        # Arguments pointing the primary queues to the DLE
        dlq_args = {
            "x-dead-letter-exchange": settings.DEAD_LETTER_EXCHANGE_NAME,
            "x-dead-letter-routing-key": settings.FAILED_QUEUE_NAME,
        }

        # Declare Email Queue (R3.3)
        email_queue = await RABBITMQ_CHANNEL.declare_queue(
            settings.EMAIL_QUEUE_NAME, durable=True, arguments=dlq_args
        )
        await email_queue.bind(
            NOTIFICATION_EXCHANGE, routing_key=NotificationType.EMAIL
        )
        logging.info(f"Email queue '{settings.EMAIL_QUEUE_NAME}' is now DLQ-enabled.")

        # Declare Push Queue (R3.3)
        push_queue = await RABBITMQ_CHANNEL.declare_queue(
            settings.PUSH_QUEUE_NAME, durable=True, arguments=dlq_args
        )
        await push_queue.bind(NOTIFICATION_EXCHANGE, routing_key=NotificationType.PUSH)
        logging.info(f"Push queue '{settings.PUSH_QUEUE_NAME}' is now DLQ-enabled.")

    except Exception as e:
        logging.error(f"CRITICAL: Failed to connect or set up RabbitMQ. Error: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Closes external connections."""
    global RABBITMQ_CONNECTION
    if RABBITMQ_CONNECTION:
        await RABBITMQ_CONNECTION.close()
        logging.info("RabbitMQ connection closed.")


# --- 4. Helper Function: Publish Message ---


async def publish_message(
    payload: SendNotificationRequest, notification_id: str, idempotency_key: str
):
    """
    Constructs the message payload and publishes it to the appropriate queue.
    """
    global NOTIFICATION_EXCHANGE
    if not NOTIFICATION_EXCHANGE:
        raise RuntimeError("RabbitMQ Exchange is not initialized.")

    # Create the full payload for the worker (includes notification_id)
    message_payload = {
        "notification_type": payload.notification_type.value,
        "template_id": payload.template_id,
        "recipient": payload.recipient.model_dump(exclude_none=True),
        "variables": payload.variables,
        "notification_id": notification_id,
    }

    message = aio_pika.Message(
        body=json.dumps(message_payload).encode(),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        # R3.2: Use idempotency key for correlation, although it's mainly tracked in Redis
        correlation_id=idempotency_key,
    )

    routing_key = payload.notification_type.value

    # R3.3: Publish the message
    await NOTIFICATION_EXCHANGE.publish(
        message,
        routing_key=routing_key,
    )
    logging.info(f"Published message {notification_id} to queue '{routing_key}'")


# --- 5. API Endpoint (R1) ---


@app.post("/api/v1/notify", status_code=status.HTTP_202_ACCEPTED)
async def send_notification(request: Request, body: SendNotificationRequest):
    """
    (R1) Handles the notification request, checks idempotency (R3.2),
    and enqueues the job (R3.3). Returns 202 Accepted immediately.
    """
    idempotency_key = request.headers.get("Idempotency-Key")

    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'Idempotency-Key' header is required.",
        )

    # --- R3.2: Idempotency Check ---
    existing_id = await status_service.check_idempotency_key(idempotency_key)
    if existing_id:
        logging.warning(f"Idempotent request detected. Not ID: {existing_id}")
        # R3.2: Return 202 Accepted with the previously created Notification ID
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "message": "Notification already accepted and processing.",
                "notification_id": existing_id,
                "status_check_url": f"/api/v1/status/{existing_id}",
            },
        )

    # --- Generate Unique ID and Set Status ---
    notification_id = str(uuid.uuid4())

    # R3.4: Set initial status to 'pending'
    await status_service.update_status(notification_id, "pending")

    # R3.2: Lock the idempotency key (must succeed, as check passed)
    if not await status_service.set_idempotency_key(idempotency_key, notification_id):
        # This is a race condition failure, treat as idempotent
        existing_id = await status_service.check_idempotency_key(idempotency_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Idempotency key clash. Notification ID: {existing_id}",
        )

    # --- R3.3: Enqueue the Message ---
    try:
        await publish_message(body, notification_id, idempotency_key)
    except Exception as e:
        # Critical failure to queue the message. Remove lock/status.
        logging.error(f"CRITICAL: Failed to publish message to RabbitMQ: {e}")

        # Note: Cleanup would ideally involve deleting the Redis key,
        # but for simplicity and safety, we leave the status as 'pending'
        # for manual review or allow the key to expire.

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notification service unavailable. Please try again later.",
        )

    # --- R1: Return 202 Accepted ---
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "message": "Notification accepted and enqueued for processing.",
            "notification_id": notification_id,
            "status_check_url": f"/api/v1/status/{notification_id}",
        },
    )


@app.get("/api/v1/status/{notification_id}")
async def get_notification_status(notification_id: str):
    """
    (R3.4) Retrieves the current status of a notification using the ID.
    """
    status_data = await status_service.get_status(notification_id)

    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification ID not found or status has expired.",
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=status_data.model_dump(exclude_none=True),
    )
