# API Gateway Service

A FastAPI-based notification gateway that handles email and push notifications with idempotency, status tracking, and message queuing.

## Features

- 📧 **Multi-channel notifications** (Email & Push)
- 🔄 **Idempotency protection** (prevents duplicate notifications)
- 📊 **Status tracking** (track notification delivery status)
- 🐰 **Async message queuing** (RabbitMQ)
- 💾 **Redis caching** (idempotency keys and status)
- 🔒 **Dead Letter Queue** (failed message handling)

## Architecture

```
Client Request → API Gateway → RabbitMQ → Worker Services
                      ↓
                   Redis (Status & Idempotency)
```

## Tech Stack

- **FastAPI** - Web framework
- **RabbitMQ** - Message broker
- **Redis** - Cache & state management
- **Docker** - Containerization
- **Pydantic** - Data validation

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+

### Run with Docker

```bash
# Clone the repository
git clone <your-repo-url>
cd API-gateway-service

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f api_gateway
```

### Access Points

- **API Docs**: http://localhost:8000/api/docs
- **RabbitMQ Management**: http://localhost:15672 (guest/guest)
- **Health Check**: http://localhost:8000/api/v1/health

## API Endpoints

### Send Notification

```bash
POST /api/v1/notifications
```

**Headers:**

- `Idempotency-Key`: Unique request identifier (required)

**Body:**

```json
{
  "notification_type": "email",
  "template_id": "welcome_email",
  "recipient": {
    "user_id": "user_123",
    "email": "test@example.com"
  },
  "variables": {
    "name": "John Doe"
  }
}
```

**Response:**

```json
{
  "success": true,
  "message": "Notification accepted and queued",
  "data": {
    "request_id": "test-123",
    "notification_id": "a1b2c3d4-...",
    "status": "queued",
    "notification_type": "email",
    "created_at": "2025-11-11T21:52:00Z"
  }
}
```

### Get Notification Status

```bash
GET /api/v1/notifications/{notification_id}
```

**Response:**

```json
{
  "success": true,
  "message": "Status retrieved successfully",
  "data": {
    "notification_id": "a1b2c3d4-...",
    "status": "queued",
    "created_at": "2025-11-11T21:52:00Z",
    "updated_at": "2025-11-11T21:52:00Z"
  }
}
```

## Environment Variables

```env
# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# RabbitMQ
QUEUE_HOST=rabbitmq
QUEUE_PORT=5672
QUEUE_USERNAME=guest
QUEUE_PASSWORD=guest

# Queues
EMAIL_QUEUE_NAME=email.queue
PUSH_QUEUE_NAME=push.queue
FAILED_QUEUE_NAME=failed.queue
DEAD_LETTER_EXCHANGE_NAME=notifications.dlx

# App
IDEMPOTENCY_WINDOW_SECONDS=300
```

## Testing

```bash
# Send a test notification
curl -X POST http://localhost:8000/api/v1/notifications \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: test-$(date +%s)" \
  -d '{
    "notification_type": "email",
    "template_id": "welcome_email",
    "recipient": {
      "user_id": "user_123",
      "email": "test@example.com"
    },
    "variables": {
      "name": "John Doe"
    }
  }'
```

## Project Structure

```
API-gateway-service/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── api/v1/endpoints/       # API endpoints
│   ├── core/                   # Config, events, exceptions
│   ├── schemas/                # Pydantic models
│   └── services/               # Business logic
├── docker-compose.yml          # Docker services
├── Dockerfile                  # API Gateway image
└── requirements.txt            # Python dependencies
```

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (requires Redis & RabbitMQ running)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Monitoring

- **RabbitMQ Dashboard**: Monitor queues, exchanges, and messages
- **Health Endpoint**: Check service connectivity
- **Logs**: `docker-compose logs -f api_gateway`

## License

MIT
