import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)


def register_exception_handlers(app):
    """Register all exception handlers."""

    @app.exception_handler(ValidationError)
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc):
        """Handle validation errors."""
        logger.warning(f"Validation error on {request.url.path}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "message": "Validation error",
                "errors": exc.errors() if hasattr(exc, "errors") else str(exc),
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle all uncaught exceptions."""
        logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": str(exc) if settings.DEBUG else "Internal server error",
                "path": str(request.url.path),
            },
        )
