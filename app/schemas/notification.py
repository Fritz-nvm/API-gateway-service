from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class NotificationType(str, Enum):
    """Defines the allowed notification channels."""

    EMAIL = "email"
    PUSH = "push"


class Priority(str, Enum):
    """Defines notification priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


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
        default=Priority.NORMAL, description="Priority level of the notification"
    )
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Timestamp of the request (auto-generated if not provided)",
    )


class NotificationRequest(BaseModel):
    """
    Schema for POST /api/v1/notifications/ incoming request.
    CLIENT ONLY provides: notification_type, template_id, recipient, variables, meta (optional)
    SERVER generates: request_id, correlation_id, notification_id
    """

    notification_type: NotificationType = Field(
        ..., description="Channel for notification (email or push)"
    )
    template_id: str = Field(..., description="Identifier for the template to use")
    recipient: Recipient = Field(..., description="Recipient information")
    variables: Dict[str, Any] = Field(
        default_factory=dict, description="Variables for template substitution"
    )
    meta: Optional[Meta] = Field(
        default=None, description="Metadata including priority and timestamp"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "notification_type": "email",
                "template_id": "welcome_email",
                "recipient": {"user_id": "user_123", "email": "test@example.com"},
                "variables": {
                    "name": "John Doe",
                    "activation_link": "https://example.com/activate/xyz",
                },
                "meta": {"priority": "normal"},
            }
        }
    }


class QueueMessagePayload(BaseModel):
    """
    Schema for the message published to RabbitMQ.
    This includes BOTH client data AND server-generated fields.
    """

    # Server-generated fields
    request_id: str
    correlation_id: str
    notification_id: str

    # Client-provided fields
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
