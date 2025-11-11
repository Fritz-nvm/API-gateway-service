import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Header, status
from typing import Optional

from app.schemas.notification import (
    NotificationRequest,
    NotificationResponse,
    Meta,
    Priority,
)
from app.schemas.response import APIResponse
from app.services.status_service import status_service
from app.services.queue_service import publish_notification

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/notifications",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=APIResponse[NotificationResponse],
)
async def send_notification(
    request: Request,
    body: NotificationRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """
    Send a notification (email or push).

    **Required Header:**
    - `Idempotency-Key`: Unique key to prevent duplicate requests

    **Request Body:**
    - `notification_type`: Either "email" or "push"
    - `template_id`: Template identifier
    - `recipient`: Recipient information (user_id, email/push_token)
    - `variables`: Template variables as key-value pairs
    - `meta` (optional): Priority and timestamp

    **Returns:**
    - `request_id`: Request identifier (from idempotency key)
    - `notification_id`: Unique identifier for tracking
    - `status`: Current status ("queued")
    - `created_at`: Timestamp of creation
    """
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )

    # Check for duplicate request
    existing_id = await status_service.check_idempotency_key(idempotency_key)
    if existing_id:
        logger.warning(f"⚠️ Duplicate request detected: {existing_id}")

        # Get existing notification data
        existing_status = await status_service.get_status(existing_id)

        return APIResponse(
            success=True,
            message="Notification already accepted",
            data=NotificationResponse(
                request_id=idempotency_key,
                notification_id=existing_id,
                status="queued",
                notification_type=body.notification_type,
                created_at=datetime.utcnow(),
                message="Notification already queued",
            ),
        )

    # Generate server-side IDs
    notification_id = str(uuid.uuid4())
    request_id = idempotency_key  # Use idempotency key as request_id
    correlation_id = str(uuid.uuid4())  # Generate correlation ID for tracing

    # Ensure meta is set with defaults
    if body.meta is None:
        body.meta = Meta(priority=Priority.NORMAL, timestamp=datetime.utcnow())
    elif body.meta.timestamp is None:
        body.meta.timestamp = datetime.utcnow()

    # Set initial status
    await status_service.update_status(notification_id, "pending")

    # Lock idempotency key
    if not await status_service.set_idempotency_key(idempotency_key, notification_id):
        existing_id = await status_service.check_idempotency_key(idempotency_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Idempotency key conflict. Notification ID: {existing_id}",
        )

    # Publish to queue
    try:
        await publish_notification(
            payload=body,
            notification_id=notification_id,
            request_id=request_id,
            correlation_id=correlation_id,
        )
    except Exception as e:
        logger.error(f"❌ Failed to publish message: {e}")

        # Cleanup on failure
        await status_service.update_status(notification_id, "failed")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notification service temporarily unavailable",
        )

    created_at = datetime.utcnow()

    return APIResponse(
        success=True,
        message="Notification accepted and queued",
        data=NotificationResponse(
            request_id=request_id,
            notification_id=notification_id,
            status="queued",
            notification_type=body.notification_type,
            created_at=created_at,
            message="Notification queued successfully",
        ),
    )


@router.get("/notifications/{notification_id}", response_model=APIResponse[dict])
async def get_notification_status(notification_id: str):
    """
    Get notification status by ID.

    **Path Parameter:**
    - `notification_id`: The unique notification identifier

    **Returns:**
    - Current status of the notification (pending, processing, sent, failed)
    - Timestamps
    - Error message (if failed)
    """
    status_data = await status_service.get_status(notification_id)

    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found or expired",
        )

    return APIResponse(
        success=True,
        message="Status retrieved successfully",
        data=(
            status_data
            if isinstance(status_data, dict)
            else status_data.model_dump(exclude_none=True)
        ),
    )
