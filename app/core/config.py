from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

# Define the acceptable environments for type checking
Environment = Literal["development", "staging", "production"]


class Settings(BaseSettings):
    """
    Application-wide settings.
    Settings are loaded from environment variables (case-insensitive)
    or from a .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", case_sensitive=False
    )

    # --- 1. CORE APPLICATION SETTINGS ---
    PROJECT_NAME: str = "API Gateway Service"
    ENVIRONMENT: Environment = "development"
    DEBUG: bool = True
    VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- 2. SECURITY & AUTHENTICATION ---
    SECRET_KEY: str

    # --- 3. DOWNSTREAM SERVICES ---
    USER_SERVICE_URL: str
    TEMPLATE_SERVICE_URL: str

    # --- 4. MESSAGE QUEUE (RabbitMQ) ---
    QUEUE_HOST: str
    QUEUE_PORT: int = 5672
    QUEUE_USERNAME: str
    QUEUE_PASSWORD: str
    EMAIL_QUEUE_NAME: str = "email.queue"
    PUSH_QUEUE_NAME: str = "push.queue"

    # --- 5. REDIS (Caching & Rate Limiting) ---
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # Rate Limiting
    RATE_LIMIT_MAX_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Idempotency
    IDEMPOTENCY_WINDOW_SECONDS: int = 300  # 5 minutes


# Instantiate the settings object
settings = Settings()
