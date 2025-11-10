import pybreaker
from app.core.config import settings
import logging
from typing import Optional

# Set up logging for the breaker events
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Circuit Breaker Listener ---
class BreakerListener(pybreaker.CircuitBreakerListener):
    """Logs circuit breaker state changes."""

    def state_changed(
        self, breaker: pybreaker.CircuitBreaker, old_state: str, new_state: str
    ):
        # We use logger.warning because a state change (especially to OPEN) is a significant event.
        logger.warning(
            f"CIRCUIT BREAKER CHANGE: Service '{breaker.name}' switched from "
            f"'{old_state}' to '{new_state}'. "
            f"New requests will be short-circuited for {breaker.reset_timeout} seconds."
        )


# --- Global Circuit Breaker Instance ---
# R4.1: This breaker is applied to all synchronous, blocking calls to external services.
user_service_breaker: Optional[pybreaker.CircuitBreaker] = None

# We defer initialization to allow settings to fully load, but we can set defaults here.
user_service_breaker = pybreaker.CircuitBreaker(
    # The number of consecutive failures before the breaker opens (Default: 5)
    fail_max=settings.CIRCUIT_BREAKER_MAX_FAILURES,
    # The time in seconds the breaker will stay open before resetting to HALF-OPEN state (Default: 30)
    reset_timeout=settings.CIRCUIT_BREAKER_RESET_TIMEOUT,
    name="User/Template Service Breaker",
    # Add the listener for logging state changes
    listeners=[BreakerListener()],
)
