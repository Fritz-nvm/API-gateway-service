import logging
from datetime import datetime
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Header, status

from app.schemas.notification import (
    NotificationRequest,
    NotificationResponse,
    NotificationStatusResponse,
)
from app.schemas.response import APIResponse
from app.services.status_service import status_service
from app.services.queue_service import publish_notification

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/notifications", response_model=APIResponse[NotificationResponse])
async def send_notification(
    request: Request,
    payload: NotificationRequest,
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
):
    """
    Send a notification (email or push).

    **Required Headers:**
    - `Idempotency-Key`: Unique key to prevent duplicate requests (5-minute window)

    **Request Body:**
    ```json
    {
      "notification_type": "email",
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "template_code": "welcome_email",
      "variables": {
        "name": "John Doe",
        "link": "https://example.com/activate"
      },
      "request_id": "req_123abc",
      "priority": 5,
      "metadata": {
        "campaign_id": "campaign_001",
        "source": "web"
      }
    }
    ```

    **Returns:**
    - 200: Notification queued successfully
    - 400: Validation error
    - 409: Duplicate request (idempotency key already used)
    - 503: Service unavailable (Redis/RabbitMQ down)
    """
    # Validate idempotency key
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )

    # Get correlation ID from request state (set by middleware)
    correlation_id = getattr(request.state, "correlation_id", str(uuid4()))

    logger.info(
        f"📨 Received notification request",
        extra={
            "correlation_id": correlation_id,
            "notification_type": payload.notification_type,
            "user_id": payload.user_id,
            "template_code": payload.template_code,
        },
    )

    # Check idempotency
    existing_id = await status_service.check_idempotency_key(idempotency_key)
    if existing_id:
        logger.info(
            f"🔄 Duplicate request detected, returning existing notification",
            extra={
                "correlation_id": correlation_id,
                "notification_id": existing_id,
                "idempotency_key": idempotency_key,
            },
        )
        # Return cached response
        cached_status = await status_service.get_status(existing_id)
        if cached_status:
            return APIResponse(
                success=True,
                message="Notification already processed (duplicate request)",
                data=NotificationResponse(**cached_status),
            )

    # Generate IDs
    notification_id = f"notif_{uuid4().hex[:12]}"
    request_id = payload.request_id or f"req_{uuid4().hex[:12]}"

    # Set idempotency key
    await status_service.set_idempotency_key(idempotency_key, notification_id)

    # Create response object
    response_data = NotificationResponse(
        request_id=request_id,
        notification_id=notification_id,
        status="queued",
        notification_type=payload.notification_type,
        created_at=datetime.utcnow(),
        message="Notification queued successfully",
    )

    # Store initial status
    await status_service.set_initial_status(response_data.model_dump())

    # Publish to queue
    try:
        await publish_notification(payload, notification_id, request_id, correlation_id)

        logger.info(
            f"✅ Notification queued successfully",
            extra={
                "correlation_id": correlation_id,
                "notification_id": notification_id,
                "request_id": request_id,
            },
        )
    except Exception as e:
        logger.error(
            f"❌ Failed to queue notification: {e}",
            extra={
                "correlation_id": correlation_id,
                "notification_id": notification_id,
            },
        )
        # Update status to failed
        await status_service.update_status(
            notification_id, "failed", error_message=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to queue notification. Please try again later.",
        )

    return APIResponse(
        success=True,
        message="Notification queued successfully",
        data=response_data,
    )


@router.get(
    "/notifications/{notification_id}",
    response_model=APIResponse[NotificationStatusResponse],
)
async def get_notification_status(notification_id: str):
    """
    Get notification status by ID.

    **Path Parameter:**
    - `notification_id`: The unique notification identifier

    **Returns:**
    - Current status of the notification (queued, processing, delivered, failed)
    - Timestamps
    - Error message (if failed)
    """
    status_data = await status_service.get_status(notification_id)

    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found or expired (24-hour TTL)",
        )

    return APIResponse(
        success=True,
        message="Status retrieved successfully",
        data=NotificationStatusResponse(**status_data),
    )


@router.post(
    "/notifications/{notification_id}/status",
    response_model=APIResponse[NotificationStatusResponse],
)
async def update_notification_status(
    notification_id: str,
    new_status: str,
    timestamp: Optional[datetime] = None,
    error: Optional[str] = None,
):
    """
    Update notification status (called by worker services).

    **Path Parameter:**
    - `notification_id`: The unique notification identifier

    **Query Parameters:**
    - `new_status`: Status (queued, processing, delivered, failed)
    - `timestamp`: Optional timestamp
    - `error`: Optional error message if failed

    **Returns:**
    - Updated status information
    """
    # Validate status
    valid_statuses = ["queued", "processing", "delivered", "failed"]
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
        )

    success = await status_service.update_status(
        notification_id=notification_id,
        new_status=new_status,
        error_message=error,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found or status update failed",
        )

    updated_status = await status_service.get_status(notification_id)

    return APIResponse(
        success=True,
        message="Status updated successfully",
        data=NotificationStatusResponse(**updated_status),
    )
