#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
import pandas as pd
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.twitter_playwright import TwitterScraper

def main():
    """
    Test extraction for a specific user.
    """
    # Test parameters
    username = "KarinHerreraVP"
    max_tweets = 30
    min_tweets = 5
    max_scrolls = 10
    
    print(f"\n===== Testing extraction for @{username} =====")
    
    # Extract tweets
    with TwitterScraper(bypass_login=True) as scraper:
        print(f"Extracting tweets from user @{username}...")
        
        df = scraper.extract_by_user(
            username=username,
            max_tweets=max_tweets,
            min_tweets=min_tweets,
            max_scrolls=max_scrolls
        )
        
        # Display results
        print(f"Extracted {len(df)} tweets from user @{username}")
        
        if not df.empty:
            print("\nSample tweets:")
            for i, row in df.head(5).iterrows():
                timestamp = row.get('timestamp', 'No date')
                print(f"- [{timestamp}] {row['usuario']}: {row['texto'][:100]}...")
            
            # Save results to CSV
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = f"user_{username}_{timestamp}.csv"
            df.to_csv(csv_path, index=False)
            print(f"Results saved to {csv_path}")
            
            # Show all timestamps
            if 'timestamp' in df.columns:
                print("\nAll timestamps:")
                for ts in df['timestamp'].values:
                    print(f"- {ts}")
        else:
            print("No tweets found.")

if __name__ == "__main__":
    main() 