import uuid
import logging
from fastapi import APIRouter, Request, HTTPException, Header, status
from typing import Optional

from app.schemas.notification import NotificationRequest
from app.schemas.response import APIResponse, NotificationResponse
from app.services.status_service import status_service
from app.services.queue_service import publish_notification

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/notifications", status_code=status.HTTP_202_ACCEPTED, response_model=APIResponse
)
async def send_notification(
    request: Request,
    body: NotificationRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """Send a notification (email or push)."""

    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )

    # Check for duplicate request
    existing_id = await status_service.check_idempotency_key(idempotency_key)
    if existing_id:
        logger.warning(f"Duplicate request detected: {existing_id}")
        return APIResponse(
            success=True,
            message="Notification already accepted",
            data=NotificationResponse(
                notification_id=existing_id,
                status="pending",
                status_url=f"/api/v1/notifications/{existing_id}",
            ),
        )

    # Generate notification ID
    notification_id = str(uuid.uuid4())

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
        await publish_notification(body, notification_id, idempotency_key)
    except Exception as e:
        logger.error(f"Failed to publish message: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notification service temporarily unavailable",
        )

    return APIResponse(
        success=True,
        message="Notification accepted and queued",
        data=NotificationResponse(
            notification_id=notification_id,
            status="pending",
            status_url=f"/api/v1/notifications/{notification_id}",
        ),
    )


@router.get("/notifications/{notification_id}", response_model=APIResponse)
async def get_notification_status(notification_id: str):
    """Get notification status by ID."""

    status_data = await status_service.get_status(notification_id)

    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found or expired",
        )

    return APIResponse(
        success=True,
        message="Status retrieved",
        data=(
            status_data
            if isinstance(status_data, dict)
            else status_data.model_dump(exclude_none=True)
        ),
    )
