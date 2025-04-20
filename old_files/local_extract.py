#!/usr/bin/env python3
"""
Local Tweet Extraction Script

This script extracts tweets from specified Twitter users using the TwitterPlaywrightScraper.
It handles authentication and outputs results to a CSV file.
"""

import os
import sys
import logging
import asyncio
import pandas as pd
from datetime import datetime
from app.services.twitter_playwright import TwitterPlaywrightScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("local_extract")

# Create output directory
output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(output_dir, exist_ok=True)

async def extract_tweets(username, max_tweets=10, min_tweets=5, max_scrolls=5):
    """
    Extract tweets from the specified user profile.
    
    Args:
        username (str): Twitter username to extract tweets from
        max_tweets (int): Maximum number of tweets to extract
        min_tweets (int): Minimum number of tweets to extract
        max_scrolls (int): Maximum number of scrolls to perform
        
    Returns:
        DataFrame: Pandas DataFrame containing extracted tweets
    """
    logger.info(f"Starting tweet extraction for user: {username}")
    logger.info(f"Parameters: max_tweets={max_tweets}, min_tweets={min_tweets}, max_scrolls={max_scrolls}")
    
    # Check for Twitter cookies to bypass login
    cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "twitter_cookies.json")
    has_cookies = os.path.exists(cookies_path)
    logger.info(f"Twitter cookies found: {has_cookies}")
    
    # Create Twitter scraper instance with correct parameters
    twitter_scraper = TwitterPlaywrightScraper(
        bypass_login=True if has_cookies else False
    )
    
    try:
        # Set environment variable for headless mode
        os.environ["DOCKER_ENVIRONMENT"] = "1"
        
        # Extract tweets
        logger.info(f"Extracting tweets for @{username}")
        tweets_df = await twitter_scraper.extract_by_user(
            username=username,
            max_tweets=max_tweets,
            min_tweets=min_tweets,
            max_scrolls=max_scrolls
        )
        
        # Check if tweets were extracted
        if tweets_df is not None and not tweets_df.empty:
            logger.info(f"Successfully extracted {len(tweets_df)} tweets")
            return tweets_df
        else:
            logger.warning(f"No tweets were extracted for @{username}")
            return pd.DataFrame()
            
    except Exception as e:
        logger.error(f"Error extracting tweets: {str(e)}")
        raise
    finally:
        # Clean up resources
        await twitter_scraper.close()
        logger.info("Twitter scraper resources released")

def main():
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: python local_extract.py <username> [max_tweets] [min_tweets] [max_scrolls]")
        sys.exit(1)
    
    username = sys.argv[1]
    max_tweets = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    min_tweets = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    max_scrolls = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    
    # Create timestamp for output file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"{username}_{timestamp}.csv")
    
    logger.info(f"Starting extraction process for user @{username}")
    
    try:
        # Set up event loop and run extraction
        loop = asyncio.get_event_loop()
        tweets_df = loop.run_until_complete(
            extract_tweets(username, max_tweets, min_tweets, max_scrolls)
        )
        
        # Save results
        if not tweets_df.empty:
            tweets_df.to_csv(output_file, index=False)
            logger.info(f"Extraction complete. Results saved to {output_file}")
            print(f"\nExtracted {len(tweets_df)} tweets from @{username}")
            print(f"Results saved to: {output_file}")
            print("\nFirst 5 tweets:")
            print(tweets_df.head().to_string())
        else:
            logger.warning("No tweets extracted. No output file created.")
            print("No tweets were extracted.")
    
    except Exception as e:
        logger.error(f"Extraction failed: {str(e)}")
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 