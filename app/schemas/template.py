from pydantic import BaseModel, Field
from typing import Dict, Any


class TemplateMetadata(BaseModel):
    """
    R2.1: Schema for the metadata returned by the downstream Template Service.
    This ensures the template exists and provides information necessary for validation
    or future enrichment by the workers.
    """

    template_id: str = Field(..., description="Unique identifier for the template.")
    name: str = Field(..., description="Human-readable name of the template.")
    required_variables: Dict[str, str] = Field(
        ...,
        description="Dictionary mapping required variable names to their expected data type (e.g., {'name': 'string', 'amount': 'number'}).",
    )
    is_active: bool = Field(
        True, description="Indicates if the template is currently active and usable."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "template_id": "welcome_email_01",
                "name": "User Welcome Email",
                "required_variables": {"user_name": "string", "login_url": "string"},
                "is_active": True,
            }
        }
