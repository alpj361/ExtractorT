#!/bin/bash
# Run Docker container with Twitter cookies authentication

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

# Set image name
IMAGE_NAME="extractor"

# Check if the image exists, build if it doesn't
if ! docker image inspect $IMAGE_NAME &> /dev/null; then
    echo "Docker image '$IMAGE_NAME' not found. Building it now..."
    docker build --platform=linux/amd64 -t $IMAGE_NAME .
fi

# Stop and remove existing container if it exists
if docker container inspect extractor_container &> /dev/null; then
    echo "Stopping and removing existing container..."
    docker stop extractor_container
    docker rm extractor_container
fi

# Check if twitter_cookies.json exists
if [ ! -f "$(pwd)/twitter_cookies.json" ]; then
    echo "Error: twitter_cookies.json file not found. This file is required for authentication."
    exit 1
fi

echo "Found Twitter cookies file. Container will use it for authentication."

# Detect if running on ARM architecture
ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" || "$ARCH" == "aarch64" ]]; then
    echo "Detected ARM64 architecture (Apple Silicon). Using --platform=linux/amd64 for compatibility."
    PLATFORM_FLAG="--platform=linux/amd64"
else
    PLATFORM_FLAG=""
fi

# Run the container with Twitter cookies
echo "Starting container with Twitter cookies authentication..."
docker run -d \
  $PLATFORM_FLAG \
  -e DOCKER_ENVIRONMENT=1 \
  -v "$(pwd)/twitter_cookies.json:/app/cookies/twitter_cookies.json" \
  -p 8000:8000 \
  --name extractor_container \
  $IMAGE_NAME

echo "Container started. To check its logs, run: docker logs extractor_container"
echo "API should be available at: http://localhost:8000" 