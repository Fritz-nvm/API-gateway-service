import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.events import startup_handler, shutdown_handler
from app.api.v1.router import api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- App Initialization ---
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ⚠️ CRITICAL: Register event handlers
@app.on_event("startup")
async def on_startup():
    """Startup event handler."""
    logger.info("🔥 FastAPI startup event triggered")
    await startup_handler()


@app.on_event("shutdown")
async def on_shutdown():
    """Shutdown event handler."""
    logger.info("🔥 FastAPI shutdown event triggered")
    await shutdown_handler()


# API Routes
app.include_router(api_router, prefix="/api/v1")


# Root Endpoint
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with service information."""
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "status": "running",
        "docs": "/api/docs",
    }
