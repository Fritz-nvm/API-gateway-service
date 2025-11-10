from fastapi import APIRouter, HTTPException, Depends, status
import uuid
from datetime import datetime
import pybreaker
import httpx
from typing import Dict, Any, Optional

# Core imports
from app.core.config import settings

# Schema imports
from app.schemas.notification import (
    NotificationRequest,
    NotificationType,
    QueueMessagePayload,
    NotificationResponse,
    NotificationStatusResponse,
    Recipient,
    Meta,
)
from app.schemas.response import APIResponse, PaginationMeta

# Service imports
from app.services.idempotency_service import idempotency_service
from app.services.user_service import user_service
from app.services.template_service import (
    template_service,
)  # <-- Still need to define this service
from app.services.queue_service import queue_service
from app.services.status_service import status_service

router = APIRouter()


# Placeholder for Authentication dependency
async def authenticate_user():
    """Placeholder for a real authentication check (R1.1)."""
    # NOTE: This should be replaced with actual token validation logic
    return True


@router.post(
    "/notifications/send",
    response_model=APIResponse[NotificationResponse],
    status_code=status.HTTP_202_ACCEPTED,  # R1.4: Asynchronous processing acceptance
)
async def send_notification(
    request: NotificationRequest, auth_check: bool = Depends(authenticate_user)
):

    # Generate ID and timestamp early, as they are needed for idempotency check and response
    current_time = datetime.utcnow()
    notification_id = f"notif_{uuid.uuid4().hex[:12]}"

    # 1. Idempotency Check (R3.1)
    already_processed, existing_notif_id = (
        await idempotency_service.check_and_store_idempotency_key(
            request_id=request.request_id, notification_id=notification_id
        )
    )

    if already_processed:
        # R3.1: If already processed, retrieve cached status and return the result of the original request.
        cached_status = await status_service.get_status(existing_notif_id)

        if cached_status:
            # Successfully retrieved existing status
            response_data = NotificationResponse(
                request_id=cached_status.get("request_id", request.request_id),
                notification_id=cached_status.get("notification_id", existing_notif_id),
                notification_type=NotificationType(cached_status["notification_type"]),
                created_at=datetime.fromisoformat(cached_status["created_at"]),
                status=cached_status["status"],
            )
        else:
            # Status has expired in Redis, but idempotency key exists. Safely return 'queued' status.
            response_data = NotificationResponse(
                request_id=request.request_id,
                notification_id=existing_notif_id,
                notification_type=request.notification_type,
                created_at=current_time,
                status="queued",
            )

        # Return 202 ACCEPTED (same as successful queueing) for true idempotency
        return APIResponse(
            success=True,
            message=f"Idempotent request: Notification {existing_notif_id} status retrieved.",
            data=response_data,
            meta=PaginationMeta(total=1),
        )

    # 2. Synchronous Lookups (User & Template)
    user_data: Optional[Dict[str, Any]] = None

    try:
        # R2.2 & R2.3: Call User Service to get contact info AND preferences
        user_data = await user_service.get_user_data_and_preferences(
            str(request.user_id)
        )

        # R2.1: Call Template Service for validation
        # TODO: Await template_service.get_template_metadata(request.template_id)
        # This line remains commented until template_service is implemented.

    except pybreaker.CircuitBreakerError:
        # R4.1: Handle circuit breaker trip
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User Service is temporarily unavailable (Circuit Breaker OPEN).",
        )
    except httpx.HTTPStatusError as e:
        # Translate 4xx/5xx errors into user-facing errors
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {request.user_id} not found.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"User service returned error: {e.response.text}",
        )
    except httpx.RequestError:
        # Handle connection, DNS, or timeout errors
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="User service connection failed or timed out.",
        )

    # 3. Preference Check (R2.4)
    user_prefs = user_data.get("preferences", {})

    if request.notification_type == NotificationType.EMAIL and not user_prefs.get(
        "email"
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="User opted out of email."
        )

    # Check if contact info exists (required even if opted-in)
    if request.notification_type == NotificationType.EMAIL and not user_data.get(
        "email"
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="User has no email address configured."
        )

    if request.notification_type == NotificationType.PUSH and not user_prefs.get(
        "push"
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="User opted out of push.")

    # Check if contact info exists
    if request.notification_type == NotificationType.PUSH and not user_data.get(
        "push_token"
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="User has no push token configured."
        )

    # 4. Message Payload Construction (R3.2 - Build the full message)

    # Build Recipient object from fetched data (R2.2, R2.3)
    recipient_obj = Recipient(
        user_id=str(request.user_id),
        email=user_data.get("email"),
        push_token=user_data.get("push_token"),
    )

    # Build Meta object
    meta_obj = Meta(priority=request.priority, timestamp=current_time)

    payload = QueueMessagePayload(
        request_id=request.request_id,
        correlation_id=request.correlation_id,
        notification_id=notification_id,
        notification_type=request.notification_type,
        template_id=request.template_id,
        recipient=recipient_obj,
        variables=request.variables,
        meta=meta_obj,
        template_validated=False,  # Will be set to True once R2.1 is integrated
        user_preferences_checked=True,
        queued_at=current_time,
    )

    # 5. Asynchronous Publishing (R3.3)
    try:
        # R3.3: Publish the comprehensive payload to the message queue
        await queue_service.publish_notification(payload)
    except HTTPException as e:
        # The QueueService raises 500/503 HTTPExceptions directly
        print(f"CRITICAL: Failed to publish message (HTTP {e.status_code}): {e.detail}")
        raise e
    except Exception as e:
        # Catch any unexpected critical failures
        print(f"CRITICAL: Unexpected failure during queue publishing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue notification due to an internal messaging failure.",
        )

    # 6. Return Response (R1.4, R3.4)
    response_data = NotificationResponse(
        request_id=request.request_id,
        notification_id=notification_id,
        notification_type=request.notification_type,
        created_at=current_time,
        status="queued",
    )

    # R3.4: Set initial status in Redis
    await status_service.set_initial_status(response_data.model_dump())

    return APIResponse(
        success=True,
        message="Notification request queued successfully.",
        data=response_data,
        meta=PaginationMeta(total=1),
    )


@router.get(
    "/notifications/{notification_id}/status",
    response_model=APIResponse[NotificationStatusResponse],
    status_code=status.HTTP_200_OK,
)
async def get_notification_status(notification_id: str):
    # This remains unchanged
    status_data = await status_service.get_status(notification_id)

    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification with ID {notification_id} not found.",
        )

    response_data = NotificationStatusResponse(**status_data)

    return APIResponse(
        success=True, message="Status retrieved successfully.", data=response_data
    )
