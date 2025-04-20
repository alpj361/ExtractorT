#!/bin/bash

# Test script for tweet extraction with automatic login
echo "===== TESTING TWITTER EXTRACTION WITH AUTO-LOGIN ====="
echo "This script will set up automatic login before testing tweet extraction"

# Check for .env file
if [ ! -f .env ]; then
    echo "Creating .env file from example template..."
    cp .env.example .env
    echo "Please edit .env file with your Twitter credentials"
    echo "Then run this script again"
    exit 1
fi

# Ensure python-dotenv is installed
pip install python-dotenv

# Step 1: Authenticate with Twitter (create or refresh storage state)
echo -e "\n1. Setting up Twitter authentication:"
python3 twitter_login.py
if [ $? -ne 0 ]; then
    echo "Login failed. Please check your credentials in .env file"
    exit 1
fi

# Step 2: Patch the Twitter scraper to use our login mechanism
echo -e "\n2. Setting up login integration:"
python3 app/services/twitter_login_integration.py
if [ $? -ne 0 ]; then
    echo "Login integration test failed"
    exit 1
fi

# Set target user (previously reported as problematic)
TEST_USER="KarinHerreraVP"
echo -e "\n3. Testing extraction for user: $TEST_USER"

# Run extraction on test profile
echo -e "\nExtracting tweets using our final script:"
python3 final_extract.py $TEST_USER 15 5 5

# Check results
if [ ! -f "${TEST_USER}_latest.csv" ]; then
    echo "Extraction failed - no CSV file was created"
    exit 1
else
    echo -e "\n===== EXTRACTION RESULTS ====="
    echo "Tweet extraction successful! Results:"
    head -n 10 ${TEST_USER}_latest.csv
fi

echo -e "\nExtraction test completed." 