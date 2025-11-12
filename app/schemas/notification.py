from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

from pydantic import BaseModel, EmailStr, Field, HttpUrl


class NotificationType(str, Enum):
    """Defines the allowed notification channels."""

    EMAIL = "email"
    PUSH = "push"


class NotificationRequest(BaseModel):
    """
    Incoming notification request schema (aligned with requirements).
    """

    notification_type: NotificationType
    user_id: str = Field(..., description="User UUID")
    template_code: str = Field(..., description="Template identifier or path")
    variables: Dict[str, Any] = Field(
        default_factory=dict, description="Template variables for substitution"
    )
    request_id: Optional[str] = Field(
        None,
        description="Optional request ID for tracking (auto-generated if not provided)",
    )
    priority: int = Field(
        default=5, ge=1, le=10, description="Priority level: 1 (highest) to 10 (lowest)"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional metadata (campaign_id, source, etc.)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "notification_type": "email",
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "template_code": "welcome_email",
                "variables": {
                    "name": "John Doe",
                    "link": "https://example.com/activate",
                },
                "request_id": "req_123abc",
                "priority": 5,
                "metadata": {"campaign_id": "campaign_001", "source": "web"},
            }
        }


class UserData(BaseModel):
    """User data for template variables (as per requirements)."""

    name: str
    link: HttpUrl
    meta: Optional[Dict[str, Any]] = None


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
    user_id: str
    template_code: str
    variables: Dict[str, Any]
    priority: int
    metadata: Optional[Dict[str, Any]] = None

    # Enriched data from services (to be filled by worker services)
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

    model_config = {
        "json_schema_extra": {
            "example": {
                "request_id": "req_12345",
                "notification_id": "notif_98765",
                "status": "delivered",
                "notification_type": "email",
                "created_at": "2025-11-10T12:34:56Z",
                "updated_at": "2025-11-10T12:35:30Z",
                "error_message": None,
            }
        }
    }


class NotificationStatus(str, Enum):
    """Notification status values (as per requirements)."""

    DELIVERED = "delivered"
    PENDING = "pending"
    FAILED = "failed"
    QUEUED = "queued"
    PROCESSING = "processing"
