#!/bin/bash

# Test script for tweet extraction
echo "===== TESTING TWEET EXTRACTION ====="
echo "This script will test extraction with various profiles to verify improvements"

# Set target user (previously reported as problematic)
TEST_USER="KarinHerreraVP"
echo "Testing extraction for user: $TEST_USER"

# Run with the new solution
echo -e "\n1. Testing with final_extract.py:"
python3 final_extract.py $TEST_USER 15 5 5

# For comparison, also test with API extraction
echo -e "\n2. Testing with api_extract.py:"
python3 api_extract.py $TEST_USER --count 15

# Compare results
echo -e "\n===== COMPARING RESULTS ====="
echo "Comparing the most recent tweets from both methods:"
head -n 10 ${TEST_USER}_latest.csv
echo -e "\nExtraction test completed. Check the CSV files for detailed results." 