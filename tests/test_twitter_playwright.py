#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import asyncio
import pandas as pd
from datetime import datetime

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.twitter_playwright import TwitterScraper

def test_hashtag_extraction():
    """
    Test the extract_by_hashtag method of the TwitterScraper class.
    """
    print("\n===== Testing hashtag extraction =====")
    
    # Test parameters
    hashtag = "python"
    max_tweets = 20
    min_tweets = 5
    
    print(f"Extracting tweets with hashtag #{hashtag}...")
    
    # Extract tweets
    with TwitterScraper(bypass_login=True) as scraper:
        df = scraper.extract_by_hashtag(
            hashtag=hashtag,
            max_tweets=max_tweets,
            min_tweets=min_tweets
        )
        
        # Display results
        print(f"Extracted {len(df)} tweets with hashtag #{hashtag}")
        
        if not df.empty:
            print("\nSample tweets:")
            for i, row in df.head(3).iterrows():
                print(f"- {row['usuario']}: {row['texto'][:50]}...")
            
            # Save results to CSV
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = f"hashtag_{hashtag}_{timestamp}.csv"
            df.to_csv(csv_path, index=False)
            print(f"Results saved to {csv_path}")
        
        return df

def test_user_extraction():
    """
    Test the extract_by_user method of the TwitterScraper class.
    """
    print("\n===== Testing user extraction =====")
    
    # Test parameters
    username = "elonmusk"  # Example username
    max_tweets = 20
    min_tweets = 5
    
    print(f"Extracting tweets from user @{username}...")
    
    # Extract tweets
    with TwitterScraper(bypass_login=True) as scraper:
        df = scraper.extract_by_user(
            username=username,
            max_tweets=max_tweets,
            min_tweets=min_tweets
        )
        
        # Display results
        print(f"Extracted {len(df)} tweets from user @{username}")
        
        if not df.empty:
            print("\nSample tweets:")
            for i, row in df.head(3).iterrows():
                print(f"- {row['usuario']}: {row['texto'][:50]}...")
            
            # Save results to CSV
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = f"user_{username}_{timestamp}.csv"
            df.to_csv(csv_path, index=False)
            print(f"Results saved to {csv_path}")
        
        return df

def main():
    """
    Main function to run the tests.
    """
    print("Starting Twitter Playwright Scraper Tests")
    
    # Test hashtag extraction
    test_hashtag_extraction()
    
    # Test user extraction
    test_user_extraction()
    
    print("\nAll tests completed!")

if __name__ == "__main__":
    main() 