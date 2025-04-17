#!/bin/bash
# Script to build and test the Docker container for the Twitter Scraper

# Exit on error
set -e

echo "Building Docker image..."
docker buildx build --platform linux/amd64 -t twitter-scraper .

echo "Running Docker container..."
docker run --platform linux/amd64 --rm -it \
  -v "$(pwd)/chrome_profile:/chrome_profile" \
  -v "$(pwd)/twitter_cookies.json:/app/cookies/twitter_cookies.json" \
  twitter-scraper

echo "Docker container test completed." 