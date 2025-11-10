import httpx
from typing import Dict, Any, List
from app.core.config import settings
from app.core.circuit_breaker import (
    user_service_breaker,
)  # Reusing the global breaker instance for Template Service
from app.schemas.template import TemplateMetadata
from fastapi import HTTPException

# Shared client instance, defined in user_service.py's global scope, but safe to redefine if user_service.py is not imported globally
# HTTP_CLIENT = httpx.AsyncClient(timeout=5.0)
# For safety, let's redefine the shared client instance here since we rely on it:
HTTP_CLIENT = httpx.AsyncClient(timeout=5.0)


class TemplateService:
    def __init__(self):
        # R2.1: Use the configured URL for the Template Service
        self.base_url = settings.TEMPLATE_SERVICE_URL
        if not self.base_url:
            # Although main.py uses default settings, we enforce the URL here
            raise ValueError("Template Service URL is not configured.")

    @user_service_breaker  # R4.1: Applying the Circuit Breaker for resilience
    async def get_template_metadata(self, template_id: str) -> TemplateMetadata:
        """
        R2.1: Fetches metadata for a specific template from the Template Service.

        Raises:
            httpx.HTTPStatusError: If the downstream service returns 4xx/5xx (e.g., 404 for missing template).
            httpx.RequestError: If connection fails.
        """
        # Assuming the Template Service has an endpoint for metadata lookup
        url = f"{self.base_url}/api/v1/templates/{template_id}/metadata"

        response = await HTTP_CLIENT.get(url)

        # This will raise httpx.HTTPStatusError for 4xx/5xx statuses
        response.raise_for_status()

        # Validate and return the response data using the Pydantic schema
        response_data = response.json().get("data", {})
        return TemplateMetadata(**response_data)

    async def validate_template_variables(
        self, template_metadata: TemplateMetadata, provided_variables: Dict[str, Any]
    ) -> bool:
        """
        Performs local validation to ensure all required variables are present.
        """
        required_keys = set(template_metadata.required_variables.keys())
        provided_keys = set(provided_variables.keys())

        if not required_keys.issubset(provided_keys):
            missing_keys = required_keys - provided_keys
            raise ValueError(
                f"Missing required variables for template '{template_metadata.template_id}': {list(missing_keys)}"
            )

        return True


# Instantiate service for use in handlers
template_service = TemplateService()
