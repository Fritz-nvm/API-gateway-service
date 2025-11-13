from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional
import os


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

    # CORE APPLICATION SETTINGS ---
    PROJECT_NAME: str = "API Gateway Service"
    ENVIRONMENT: Environment = "development"
    DEBUG: bool = True
    VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # SECURITY & AUTHENTICATION ---
    SECRET_KEY: str

    # Microservice URLs
    USER_SERVICE_URL: str = "http://user-service:8001"
    TEMPLATE_SERVICE_URL: str = "http://template-service:8002"
    EMAIL_SERVICE_URL: str = "http://email-service:8003"
    PUSH_SERVICE_URL: str = "http://push-service:8004"

    # MESSAGE QUEUE (RabbitMQ) ---
    QUEUE_HOST: str
    QUEUE_PORT: int = 5672
    QUEUE_USERNAME: str
    QUEUE_PASSWORD: str
    EMAIL_QUEUE_NAME: str = "email.queue"
    PUSH_QUEUE_NAME: str = "push.queue"

    FAILED_QUEUE_NAME: str = "failed.queue"
    DEAD_LETTER_EXCHANGE_NAME: str = "dead.letter.exchange"

    @property  # <-- ADDED: Critical for workers connecting to RabbitMQ
    def QUEUE_URL(self) -> str:
        """
        Build a robust AMQP URL.

        - Prefer explicit QUEUE_URL / AMQP_URL env var (providers often supply this).
        - Tolerate QUEUE_HOST values that already include a scheme, credentials or port.
        - Prefer environment credentials (QUEUE_USERNAME/QUEUE_PASSWORD) when present.
        """
        # 1) explicit URL takes precedence
        env_url = os.getenv("QUEUE_URL") or os.getenv("AMQP_URL")
        if env_url:
            return env_url

        # 2) gather components (env overrides settings)
        raw_host = os.getenv("QUEUE_HOST", self.QUEUE_HOST)
        port = os.getenv("QUEUE_PORT", str(self.QUEUE_PORT))
        user = os.getenv("QUEUE_USERNAME", self.QUEUE_USERNAME)
        pwd = os.getenv("QUEUE_PASSWORD", self.QUEUE_PASSWORD)

        # 3) strip any leading scheme and any embedded credentials to avoid duplication
        if raw_host.startswith("amqp://") or raw_host.startswith("amqps://"):
            raw_host = raw_host.split("://", 1)[1]
        if "@" in raw_host:
            raw_host = raw_host.split("@", 1)[1]

        # 4) ensure we have host and port (raw_host may already contain :port)
        if ":" in raw_host:
            host_only, host_port = raw_host.rsplit(":", 1)
        else:
            host_only, host_port = raw_host, port

        # 5) prefer explicit username/password if provided; otherwise omit credentials
        creds = ""
        if user and pwd:
            creds = f"{user}:{pwd}@"

        return f"amqp://{creds}{host_only}:{host_port}/"

    # --- 5. REDIS (Caching & Rate Limiting) ---
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    @property
    def REDIS_URL(self) -> str:
        """Resolve Redis URL. Prefer explicit REDIS_URL/REDIS_URI env var, otherwise build from parts."""
        env_url = os.getenv("REDIS_URL") or os.getenv("REDIS_URI")
        if env_url:
            return env_url

        host = os.getenv("REDIS_HOST", self.REDIS_HOST)
        port = os.getenv("REDIS_PORT", str(self.REDIS_PORT))
        db = os.getenv("REDIS_DB", str(self.REDIS_DB))
        pwd = (
            os.getenv("REDIS_PASSWORD")
            or os.getenv("REDIS_PASS")
            or self.REDIS_PASSWORD
        )
        if pwd:
            return f"redis://:{pwd}@{host}:{port}/{db}"
        return f"redis://{host}:{port}/{db}"

    # Rate Limiting
    RATE_LIMIT_MAX_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Idempotency
    IDEMPOTENCY_WINDOW_SECONDS: int = 300  # 5 minutes

    # Circuit Breaker Settings
    CIRCUIT_BREAKER_MAX_FAILURES: int = 5
    CIRCUIT_BREAKER_RESET_TIMEOUT: int = 30


settings = Settings()
