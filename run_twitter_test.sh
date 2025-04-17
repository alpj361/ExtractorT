#!/bin/bash

# Ensure script fails on error
set -e

# Print header
echo "===================================================="
echo "Twitter Playwright Scraper Test Runner"
echo "===================================================="

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# Install playwright browsers if needed
echo "Ensuring Playwright browsers are installed..."
python -m playwright install

# Run the test script
echo "Running Twitter scraper tests..."
python tests/test_twitter_playwright.py

# Print completion message
echo "===================================================="
echo "Test run completed."
echo "====================================================" 