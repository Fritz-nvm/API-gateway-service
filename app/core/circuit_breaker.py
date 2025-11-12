import pybreaker
from app.core.config import settings
import logging
from typing import Callable
from functools import wraps

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

    def failure(self, breaker: pybreaker.CircuitBreaker, exception: Exception):
        logger.error(f"❌ Circuit breaker '{breaker.name}' failure: {exception}")

    def success(self, breaker: pybreaker.CircuitBreaker):
        logger.debug(f"✅ Circuit breaker '{breaker.name}' call succeeded")


# --- Global Circuit Breaker Instances ---

user_service_breaker = pybreaker.CircuitBreaker(
    fail_max=getattr(settings, "CIRCUIT_BREAKER_MAX_FAILURES", 5),
    reset_timeout=getattr(settings, "CIRCUIT_BREAKER_RESET_TIMEOUT", 30),
    name="User/Template Service",
    listeners=[BreakerListener()],
)

rabbitmq_breaker = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=30,
    name="RabbitMQ",
    listeners=[BreakerListener()],
)

redis_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=20,
    name="Redis",
    listeners=[BreakerListener()],
)


# --- Async Circuit Breaker Decorator ---
def async_circuit_breaker(breaker: pybreaker.CircuitBreaker):
    """
    Decorator for async functions that uses pybreaker.
    Properly wraps async calls for circuit breaker protection.
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Use breaker.call() with an async-compatible wrapper
            return await breaker.call(func, *args, **kwargs)

        return wrapper

    return decorator


def sync_circuit_breaker(breaker: pybreaker.CircuitBreaker):
    """Decorator for sync functions."""

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
