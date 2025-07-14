#!/bin/bash
mkdir -p output
rm -rf output/*

# Build the Docker image
docker-compose build

# Start the services in the background
docker-compose up -d
echo "Services started. Waiting..."

# docker-compose exec client_1 /app/.venv/bin/mixnet prepare_message --message "Hello from client_1 to client_2" --sender-id client_1 --recipient-id client_2
# docker-compose exec -it client_1 /app/.venv/bin/mixnet poll-messages
sleep 20

echo "Cleaning up Docker Compose environment..."
docker-compose down -v

echo "Done."
