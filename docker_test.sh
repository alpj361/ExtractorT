#!/bin/bash

# Set variables
CONTAINER_NAME="extractor_test"
IMAGE_NAME="extractor"

# Check if container already exists and remove it
if [ "$(docker ps -aq -f name=${CONTAINER_NAME})" ]; then
    echo "Removing existing container..."
    docker rm -f ${CONTAINER_NAME}
fi

# Run container in detached mode
echo "Starting container..."
docker run -d --name ${CONTAINER_NAME} ${IMAGE_NAME}

# Copy latest Twitter cookies to container
echo "Copying Twitter cookies to container..."
docker cp twitter_cookies.json ${CONTAINER_NAME}:/app/cookies/twitter_cookies.json

# Copy the test script
echo "Copying test script to container..."
docker cp tests/test_twitter_playwright.py ${CONTAINER_NAME}:/app/tests/test_twitter_playwright.py
docker cp run_twitter_test.sh ${CONTAINER_NAME}:/app/run_twitter_test.sh
docker exec ${CONTAINER_NAME} chmod +x /app/run_twitter_test.sh

# Run the test inside the container
echo "Running Twitter Playwright test..."
docker exec -it ${CONTAINER_NAME} bash -c "cd /app && ./run_twitter_test.sh"

# Show logs from the container
echo "Container logs:"
docker logs ${CONTAINER_NAME}

# Clean up container when done
echo "Cleaning up container..."
docker rm -f ${CONTAINER_NAME}

echo "Test completed." 