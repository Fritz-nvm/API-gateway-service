from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class NotificationType(str, Enum):
    """Defines the allowed notification channels."""

    email = "email"
    push = "push"


class Priority(str, Enum):
    """Defines notification priority levels."""

    low = "low"
    normal = "normal"
    high = "high"


class Recipient(BaseModel):
    """Recipient information for the notification."""

    user_id: str = Field(..., description="Unique identifier for the user")
    email: Optional[EmailStr] = Field(
        None, description="Email address for email notifications"
    )
    push_token: Optional[str] = Field(
        None, description="FCM/push token for push notifications"
    )


class Meta(BaseModel):
    """Metadata for the notification."""

    priority: Priority = Field(
        default=Priority.normal, description="Priority level of the notification"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp of the request"
    )


class NotificationRequest(BaseModel):
    """Schema for POST /api/v1/notifications/ incoming request."""

    request_id: str = Field(..., description="Unique ID for idempotency")
    correlation_id: str = Field(..., description="ID for distributed tracing")
    notification_id: str = Field(
        ..., description="Unique identifier for this notification"
    )
    notification_type: NotificationType = Field(
        ..., description="Channel for notification (email or push)"
    )
    template_id: str = Field(..., description="Identifier for the template to use")
    recipient: Recipient = Field(..., description="Recipient information")
    variables: Dict[str, Any] = Field(
        default_factory=dict, description="Variables for template substitution"
    )
    meta: Meta = Field(
        default_factory=Meta, description="Metadata including priority and timestamp"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "request_id": "req_12345",
                "correlation_id": "corr_abcde",
                "notification_id": "notif_98765",
                "notification_type": "email",
                "template_id": "tpl_welcome_v2",
                "recipient": {
                    "user_id": "user_42",
                    "email": "user@example.com",
                    "push_token": "fcm_token_...",
                },
                "variables": {"name": "Gerard", "account_link": "https://..."},
                "meta": {"priority": "normal", "timestamp": "2025-11-10T12:34:56Z"},
            }
        }
    }


class QueueMessagePayload(BaseModel):
    """Schema for the message published to RabbitMQ/Kafka."""

    request_id: str
    correlation_id: str
    notification_id: str
    notification_type: NotificationType
    template_id: str
    recipient: Recipient
    variables: Dict[str, Any]
    meta: Meta

    # Enriched data from services
    template_validated: bool = Field(default=False)
    user_preferences_checked: bool = Field(default=False)
    queued_at: datetime = Field(default_factory=datetime.utcnow)


class NotificationResponse(BaseModel):
    """Response schema for notification creation."""

    request_id: str
    notification_id: str
    status: str = "queued"
    notification_type: NotificationType
    created_at: datetime
    message: str = "Notification queued successfully"

    model_config = {
        "json_schema_extra": {
            "example": {
                "request_id": "req_12345",
                "notification_id": "notif_98765",
                "status": "queued",
                "notification_type": "email",
                "created_at": "2025-11-10T12:34:56Z",
                "message": "Notification queued successfully",
            }
        }
    }


class NotificationStatusResponse(BaseModel):
    """Response schema for notification status check."""

    request_id: str
    notification_id: str
    status: str
    notification_type: NotificationType
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None
