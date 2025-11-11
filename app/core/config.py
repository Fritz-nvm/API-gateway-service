from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
import os  # <-- ADDED: Needed for QUEUE_URL property

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

    FAILED_QUEUE_NAME: str = "failed.queue"
    DEAD_LETTER_EXCHANGE_NAME: str = "dead.letter.exchange"

    # Full connection string derived from other variables (used by workers/queue_service and aio-pika)
    @property  # <-- ADDED: Critical for workers connecting to RabbitMQ
    def QUEUE_URL(self) -> str:
        # Use os.getenv as a fallback for the workers which are separate processes
        return (
            f"amqp://{os.getenv('QUEUE_USERNAME', self.QUEUE_USERNAME)}:"
            f"{os.getenv('QUEUE_PASSWORD', self.QUEUE_PASSWORD)}@"
            f"{os.getenv('QUEUE_HOST', self.QUEUE_HOST)}:"
            f"{os.getenv('QUEUE_PORT', str(self.QUEUE_PORT))}/"
        )

    # --- 5. REDIS (Caching & Rate Limiting) ---
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # Rate Limiting
    RATE_LIMIT_MAX_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Idempotency
    IDEMPOTENCY_WINDOW_SECONDS: int = 300  # 5 minutes

    # --- 6. CIRCUIT BREAKER (R4.1) --- # <-- ADDED: Fixes the current AttributeError
    CIRCUIT_BREAKER_MAX_FAILURES: int = 5
    CIRCUIT_BREAKER_RESET_TIMEOUT: int = 30  # seconds


# Instantiate the settings object
settings = Settings()
