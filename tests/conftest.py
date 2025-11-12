import pytest
import asyncio
import os
from typing import AsyncGenerator

# -------------------------------------------------------------------
# CRITICAL FIX: Set all required Pydantic environment variables.
# 1. Added SECRET_KEY (missing from previous run).
# 2. Mapped RABBITMQ_* names to the expected QUEUE_* names to satisfy
#    the Pydantic Settings model validation during test collection.
# -------------------------------------------------------------------
os.environ["SECRET_KEY"] = "dummy-key-for-testing-only"

os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6379"

# Map RabbitMQ settings to the expected QUEUE_* config names
os.environ["QUEUE_HOST"] = "localhost"
os.environ["QUEUE_PORT"] = "5672"
os.environ["QUEUE_USERNAME"] = "guest"
os.environ["QUEUE_PASSWORD"] = "guest"

os.environ["ENVIRONMENT"] = "development"
os.environ["LOG_LEVEL"] = "ERROR"  # Reduce noise in tests

# Try early synchronous Redis init if possible (helps imports that access the client)
try:
    # Import AFTER setting environment variables
    from app.services.status_service import status_service

    init_result = status_service.initialize_client()
    if asyncio.iscoroutine(init_result):
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                loop.run_until_complete(init_result)
        except RuntimeError:
            # no running loop available; initialization will occur in the async fixture
            pass
except Exception:
    pass


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_services(event_loop):
    """
    Initialize Redis, RabbitMQ client and run application startup handler before tests.
    Uses retries and performs a clean shutdown via the application shutdown handler.
    """
    from app.services.status_service import status_service
    from app.services.queue_service import queue_service
    from app.core.events import startup_handler, shutdown_handler

    try:
        # Redis init with retries
        print("\n🔧 Initializing Redis...")
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                init_res = status_service.initialize_client()
                if asyncio.iscoroutine(init_res):
                    await init_res
                # ensure ping works (handle sync/async)
                client = status_service.get_client()
                ping_res = client.ping()
                if asyncio.iscoroutine(ping_res):
                    await ping_res
                print("✅ Redis initialized")
                break
            except Exception as e:
                if attempt == max_retries:
                    pytest.exit(
                        f"❌ Failed to connect to Redis after {max_retries} attempts: {e}\n\n"
                        "Make sure Redis is running:\n"
                        "  docker-compose -f docker-compose.dev.yml up -d redis\n"
                        "  sleep 5"
                    )
                print(f"⚠️  Redis connection attempt {attempt} failed, retrying...")
                await asyncio.sleep(2)

        # RabbitMQ client init with retries
        print("🔧 Initializing RabbitMQ client...")
        for attempt in range(1, max_retries + 1):
            try:
                init_q = queue_service.initialize()
                if asyncio.iscoroutine(init_q):
                    await init_q
                print("✅ RabbitMQ client initialized")
                break
            except Exception as e:
                if attempt == max_retries:
                    pytest.exit(
                        f"❌ Failed to connect to RabbitMQ after {max_retries} attempts: {e}\n\n"
                        "Make sure RabbitMQ is running:\n"
                        "  docker-compose -f docker-compose.dev.yml up -d rabbitmq\n"
                        "  sleep 10  # RabbitMQ takes longer to start"
                    )
                print(f"⚠️  RabbitMQ connection attempt {attempt} failed, retrying...")
                await asyncio.sleep(3)

        # Run application startup handler to declare exchanges/queues (health depends on this)
        print("🔧 Running application startup handler (declares exchanges/queues)...")
        try:
            startup_res = startup_handler()
            if asyncio.iscoroutine(startup_res):
                await startup_res
            print("✅ Application startup handler completed")
        except Exception as e:
            pytest.exit(
                f"❌ Application startup (RabbitMQ/exchange setup) failed: {e}\n\n"
                "Make sure RabbitMQ is running:\n"
                "  docker-compose -f docker-compose.dev.yml up -d rabbitmq\n"
                "  sleep 10"
            )

        yield

    except Exception as e:
        pytest.exit(f"❌ Unexpected error during service initialization: {e}")

    finally:
        # Ensure a clean shutdown via the application's shutdown handler
        print("\n🧹 Cleaning up services...")
        try:
            shutdown_res = shutdown_handler()
            if asyncio.iscoroutine(shutdown_res):
                await shutdown_res
            print("✅ Services closed")
        except Exception as e:
            print(f"⚠️  Cleanup warning: {e}")


@pytest.fixture
def test_notification_payload():
    """Sample notification payload for testing."""
    return {
        "notification_type": "email",
        "user_id": "test-user-123",
        "template_code": "welcome_email",
        "variables": {"name": "Test User", "link": "https://example.com"},
        "priority": 5,
        "metadata": {"source": "test"},
    }
