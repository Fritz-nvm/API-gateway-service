# Start all services

docker-compose up -d

# View logs

docker-compose logs -f api_gateway

# Stop all services

docker-compose down

# Stop and remove volumes (clean slate)

docker-compose down -v

# Rebuild API Gateway after code changes

docker-compose up -d --build api_gateway

# Access RabbitMQ Management UI

# Open browser: http://localhost:15672

# Login: guest / guest

# Check service health

docker-compose ps

# Execute commands in running container

docker-compose exec api_gateway bash
