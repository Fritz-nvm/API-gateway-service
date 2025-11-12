import pybreaker
from app.core.config import settings
import logging
from typing import Optional, Callable, Any
from functools import wraps
import asyncio

# Set up logging for the breaker events
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Circuit Breaker Listener ---
class BreakerListener(pybreaker.CircuitBreakerListener):
    """Logs circuit breaker state changes."""

    def state_changed(
        self, breaker: pybreaker.CircuitBreaker, old_state: str, new_state: str
    ):
        logger.warning(
            f"⚡ CIRCUIT BREAKER: '{breaker.name}' changed from "
            f"'{old_state}' → '{new_state}' "
            f"(Reset in {breaker.reset_timeout}s)"
        )

    def before_call(
        self, breaker: pybreaker.CircuitBreaker, func: Callable, *args, **kwargs
    ):
        """Called before each protected call."""
        logger.debug(f"🔍 Circuit breaker '{breaker.name}' calling {func.__name__}")

    def failure(self, breaker: pybreaker.CircuitBreaker, exception: Exception):
        """Called when a protected call fails."""
        logger.error(
            f"❌ Circuit breaker '{breaker.name}' failure: {exception} "
            f"(Failures: {breaker.fail_counter}/{breaker.fail_max})"
        )

    def success(self, breaker: pybreaker.CircuitBreaker):
        """Called when a protected call succeeds."""
        logger.debug(f"✅ Circuit breaker '{breaker.name}' call succeeded")


# --- Global Circuit Breaker Instances ---

# User/Template Service Breaker (for external HTTP calls)
user_service_breaker = pybreaker.CircuitBreaker(
    fail_max=getattr(settings, "CIRCUIT_BREAKER_MAX_FAILURES", 5),
    reset_timeout=getattr(settings, "CIRCUIT_BREAKER_RESET_TIMEOUT", 30),
    name="User/Template Service",
    listeners=[BreakerListener()],
)

# RabbitMQ Breaker (for queue publishing)
rabbitmq_breaker = pybreaker.CircuitBreaker(
    fail_max=3,  # Fail faster for queue issues
    reset_timeout=30,
    name="RabbitMQ",
    listeners=[BreakerListener()],
)

# Redis Breaker (for cache operations)
redis_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=20,  # Shorter timeout for cache
    name="Redis",
    listeners=[BreakerListener()],
)


# --- Async Circuit Breaker Wrapper ---
def async_circuit_breaker(breaker: pybreaker.CircuitBreaker):
    """
    Decorator to apply circuit breaker pattern to async functions.

    Usage:
        @async_circuit_breaker(user_service_breaker)
        async def fetch_user_preferences(user_id: str):
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # Check circuit state before calling
                if breaker.current_state == "open":
                    logger.warning(
                        f"⚡ Circuit breaker '{breaker.name}' is OPEN, rejecting call"
                    )
                    raise pybreaker.CircuitBreakerError(
                        f"Circuit breaker '{breaker.name}' is open"
                    )

                # Call the async function
                result = await func(*args, **kwargs)

                # Record success
                breaker.call_succeeded()
                logger.debug(f"✅ Circuit breaker '{breaker.name}' call succeeded")

                return result

            except pybreaker.CircuitBreakerError:
                # Circuit is open, propagate immediately
                raise

            except Exception as e:
                # Record failure
                breaker.call_failed()
                logger.error(
                    f"❌ Circuit breaker '{breaker.name}' failure: {e} "
                    f"(Failures: {breaker.fail_counter}/{breaker.fail_max})"
                )
                raise

        return wrapper

    return decorator


def sync_circuit_breaker(breaker: pybreaker.CircuitBreaker):
    """
    Decorator to apply circuit breaker pattern to sync functions.

    Usage:
        @sync_circuit_breaker(user_service_breaker)
        def fetch_user_data(user_id: str):
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)

        return wrapper

    return decorator


# --- Helper Functions ---


def get_breaker_status(breaker: pybreaker.CircuitBreaker) -> dict:
    """Get current status of a circuit breaker."""
    return {
        "name": breaker.name,
        "state": breaker.current_state,
        "fail_counter": breaker.fail_counter,
        "fail_max": breaker.fail_max,
        "reset_timeout": breaker.reset_timeout,
    }


def get_all_breakers_status() -> dict:
    """Get status of all circuit breakers."""
    return {
        "user_service": get_breaker_status(user_service_breaker),
        "rabbitmq": get_breaker_status(rabbitmq_breaker),
        "redis": get_breaker_status(redis_breaker),
    }


def reset_all_breakers():
    """Manually reset all circuit breakers."""
    for breaker in [user_service_breaker, rabbitmq_breaker, redis_breaker]:
        try:
            breaker.close()
            logger.info(f"🔄 Circuit breaker '{breaker.name}' manually reset")
        except Exception as e:
            logger.error(f"❌ Failed to reset circuit breaker '{breaker.name}': {e}")
