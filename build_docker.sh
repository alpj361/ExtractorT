#!/bin/bash
# Script to build the Docker image

echo "Building Docker image..."
docker build -t extractor .

echo "Docker image 'extractor' built successfully."
echo "To run the container with proper Chrome profile mounting, use ./run_docker.sh" 