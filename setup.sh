#!/bin/bash
mkdir -p output
rm -rf output/*

# Build the Docker image
docker-compose build

# Start the services in the background
docker-compose up -d
echo "Services started. Waiting..."

sleep 5 # let the clients send some dummies
docker-compose exec client_1 /app/.venv/bin/mixnet prepare-message --message "Hello from client_1 to client_2" --sender-id client_1 --recipient-id client_2
sleep 4 # let the message be processed
output=$(docker-compose exec -T client_2 /app/.venv/bin/mixnet poll-messages)
echo "Output from client_2:"
echo $output
if [[ $output == *"Hello from client_1 to client_2"* ]]; then
    docker-compose exec client_2 /app/.venv/bin/mixnet prepare-message --message "Hello from client_2 to client_1" --sender-id client_2 --recipient-id client_1
fi
sleep 4 # let the message be processed
output=$(docker-compose exec -T client_1 /app/.venv/bin/mixnet poll-messages)
echo "Output from client_1:"
echo $output

echo "Cleaning up Docker Compose environment..."
docker-compose down -v

echo "Done."
