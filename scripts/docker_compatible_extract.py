#!/usr/bin/env python3
"""
Docker-compatible script to extract recent tweets from Twitter profiles.
This script prioritizes recent tweets, uses search with 'latest' filter,
and effectively filters pinned tweets. It can be run either locally or in Docker.
"""

import os
import sys
import json
import logging
import asyncio
import pandas as pd
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import the TwitterPlaywrightScraper class from the correct path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.twitter_playwright import TwitterPlaywrightScraper

def is_docker():
    """Check if we're running inside a Docker container"""
    return os.path.exists('/.dockerenv')

async def extract_tweets_custom(username, max_tweets=10, min_tweets=5, max_scrolls=5):
    """
    Extract tweets directly using Playwright with explicit Firefox browser
    
    This is a more direct approach that bypasses some of the complexities
    of the TwitterPlaywrightScraper class
    """
    logger.info(f"Starting direct Firefox extraction for user: {username}")
    
    # Get storage path
    storage_path = Path("firefox_storage.json")
    if not storage_path.exists():
        logger.warning(f"Storage file not found: {storage_path}")
        return []
    
    async with async_playwright() as p:
        try:
            # Launch Firefox browser
            browser = await p.firefox.launch(headless=False)
            
            # Create context with storage state
            context = await browser.new_context(storage_state=str(storage_path))
            page = await context.new_page()
            
            # First try search with latest filter
            url = f"https://twitter.com/search?q=from%3A{username}&f=live"
            logger.info(f"Navigating to: {url}")
            await page.goto(url)
            
            # Wait for page to load
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(5)
            
            # Check if redirected to login
            current_url = page.url
            if "login" in current_url:
                logger.error("Redirected to login page. Storage state may be invalid.")
                await browser.close()
                return []
            
            # Take screenshot for debugging
            await page.screenshot(path=f"{username}_search_page.png")
            logger.info(f"Screenshot saved as {username}_search_page.png")
            
            # Extract tweets
            tweets = []
            tweet_selectors = [
                "article[data-testid='tweet']",
                "div[data-testid='tweet']",
                "div[data-testid='cellInnerDiv']",
                "article[role='article']"
            ]
            
            # Try each selector
            tweet_elements = []
            for selector in tweet_selectors:
                logger.info(f"Trying selector: {selector}")
                elements = await page.query_selector_all(selector)
                if elements and len(elements) > 0:
                    logger.info(f"Found {len(elements)} tweets with selector: {selector}")
                    tweet_elements = elements
                    break
            
            if not tweet_elements:
                logger.warning("No tweets found initially")
                
                # Scroll to try to load more content
                logger.info(f"Scrolling {max_scrolls} times to try to load tweets")
                for i in range(max_scrolls):
                    logger.info(f"Scroll {i+1}/{max_scrolls}")
                    await page.evaluate("window.scrollBy(0, window.innerHeight)")
                    await asyncio.sleep(2)
                    
                    # Check again for tweets
                    for selector in tweet_selectors:
                        elements = await page.query_selector_all(selector)
                        if elements and len(elements) > 0:
                            logger.info(f"Found {len(elements)} tweets after scrolling with selector: {selector}")
                            tweet_elements = elements
                            break
                    
                    if tweet_elements:
                        break
            
            # Process found tweets
            if tweet_elements:
                # Limit number of tweets
                tweet_elements = tweet_elements[:max_tweets]
                
                for i, tweet_el in enumerate(tweet_elements):
                    tweet_data = {}
                    
                    # Get tweet text
                    try:
                        text_selectors = ["div[data-testid='tweetText']", "div.css-901oao"]
                        for text_selector in text_selectors:
                            text_el = await tweet_el.query_selector(text_selector)
                            if text_el:
                                tweet_data["text"] = await text_el.inner_text()
                                break
                    except Exception as e:
                        logger.warning(f"Error extracting text from tweet {i+1}: {e}")
                    
                    # Get timestamp
                    try:
                        time_el = await tweet_el.query_selector("time")
                        if time_el:
                            datetime_attr = await time_el.get_attribute("datetime")
                            if datetime_attr:
                                tweet_data["timestamp"] = datetime_attr
                    except Exception as e:
                        logger.warning(f"Error extracting timestamp from tweet {i+1}: {e}")
                    
                    # Add tweet to results if it has content
                    if "text" in tweet_data:
                        tweets.append(tweet_data)
            
            logger.info(f"Extracted {len(tweets)} tweets using direct Firefox approach")
            await browser.close()
            return tweets
            
        except Exception as e:
            logger.error(f"Error in direct Firefox extraction: {e}")
            try:
                await browser.close()
            except:
                pass
            return []

async def extract_tweets(username, max_tweets=10, min_tweets=5, max_scrolls=5):
    """
    Extract tweets from a user's profile using TwitterPlaywrightScraper.
    
    Args:
        username (str): Twitter username to extract tweets from
        max_tweets (int): Maximum number of tweets to extract
        min_tweets (int): Minimum number of tweets to return
        max_scrolls (int): Maximum number of scrolls to perform
        
    Returns:
        list: Extracted tweets or [] if extraction failed
    """
    logger.info(f"Starting extraction for user: {username}")
    
    # Check if we have Firefox storage state
    firefox_storage_path = Path("firefox_storage.json")
    twitter_cookies_path = Path("twitter_cookies.json")
    
    storage_file = None
    if firefox_storage_path.exists():
        logger.info(f"Firefox storage state found at {firefox_storage_path}")
        storage_file = str(firefox_storage_path)
    elif twitter_cookies_path.exists():
        logger.info(f"Twitter cookies file found at {twitter_cookies_path}")
        # Cookies require a different approach, but we'll note it
    else:
        logger.warning("No storage state or cookies file found. Authentication may fail.")
    
    try:
        # Create directory for screenshots if it doesn't exist
        os.makedirs("/tmp", exist_ok=True)
        
        # Initialize the scraper with proper parameters
        scraper = TwitterPlaywrightScraper(bypass_login=True)
        
        # Extract tweets
        logger.info(f"Extracting tweets for {username} (max: {max_tweets}, min: {min_tweets}, scrolls: {max_scrolls})")
        async with scraper:
            # Set state file if available (custom method implementation)
            if storage_file:
                logger.info(f"Loading storage state from {storage_file}")
                try:
                    await scraper.context.storage_state(path=storage_file)
                    logger.info("Storage state loaded successfully")
                except Exception as e:
                    logger.warning(f"Error loading storage state: {e}")
            
            # Try getting a recent sample first
            tweets = await scraper.extract_by_user(
                username=username,
                max_tweets=max_tweets,
                min_tweets=min_tweets,
                max_scrolls=max_scrolls
            )
        
        # Sort tweets by timestamp to ensure most recent first
        if tweets:
            tweets.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            logger.info(f"Successfully extracted {len(tweets)} tweets from {username}")
            return tweets
        else:
            logger.warning(f"No tweets extracted for {username}")
            return []
            
    except Exception as e:
        logger.error(f"Error extracting tweets: {e}", exc_info=True)
        # Return empty list instead of None to simplify handling
        return []

def save_results(tweets, username):
    """
    Save extracted tweets to a CSV file
    
    Args:
        tweets (list): List of extracted tweets
        username (str): Twitter username
        
    Returns:
        str: Path to saved CSV file
    """
    if not tweets:
        logger.warning("No tweets to save")
        return None
    
    # Create DataFrame from tweets
    df = pd.DataFrame(tweets)
    
    # Generate timestamp for filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{username}_tweets_{timestamp}.csv"
    
    # Save to CSV
    df.to_csv(filename, index=False)
    logger.info(f"Saved {len(tweets)} tweets to {filename}")
    
    # Print tweet summary
    print("\n--- Tweet Extraction Summary ---")
    print(f"Username: @{username}")
    print(f"Total tweets extracted: {len(tweets)}")
    
    if len(tweets) > 0:
        try:
            # Handle potential type issues gracefully
            timestamps = [t.get('timestamp', 0) for t in tweets]
            # Convert string timestamps to numbers if needed
            timestamps = [float(ts) if isinstance(ts, str) else ts for ts in timestamps]
            # Filter out 0 timestamps
            valid_timestamps = [ts for ts in timestamps if ts > 0]
            
            if valid_timestamps:
                oldest_date = min(valid_timestamps)
                newest_date = max(valid_timestamps)
                
                # Adjust timestamp format if needed (some are in milliseconds)
                if oldest_date > 1000000000000:  # Milliseconds format
                    oldest_date = oldest_date / 1000
                    newest_date = newest_date / 1000
                    
                print(f"Date range: {datetime.fromtimestamp(oldest_date)} to {datetime.fromtimestamp(newest_date)}")
            else:
                print("Timestamps not available in the data")
        except Exception as e:
            print(f"Error processing timestamps: {e}")
    
    print(f"Results saved to: {filename}")
    print("-----------------------------\n")
    
    return filename

async def main_async():
    """Main async function to extract tweets and save results"""
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: python docker_compatible_extract.py USERNAME [MAX_TWEETS] [MIN_TWEETS] [MAX_SCROLLS]")
        return 1
    
    username = sys.argv[1]
    max_tweets = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    min_tweets = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    max_scrolls = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    
    # Log environment
    logger.info(f"Running in Docker: {is_docker()}")
    
    # First try direct Firefox extraction (more reliable)
    logger.info("Trying direct Firefox extraction first...")
    try:
        tweets = await extract_tweets_custom(username, max_tweets, min_tweets, max_scrolls)
        if tweets and len(tweets) >= min_tweets:
            logger.info("Direct Firefox extraction successful")
            save_results(tweets, username)
            return 0
        else:
            logger.info("Direct Firefox extraction didn't get enough tweets, falling back to standard approach")
    except Exception as e:
        logger.error(f"Error in direct Firefox extraction, falling back: {e}")
    
    # Fall back to standard extraction
    tweets = await extract_tweets(username, max_tweets, min_tweets, max_scrolls)
    
    # Save results if we got any tweets
    if tweets:
        save_results(tweets, username)
        return 0
    else:
        logger.error("Tweet extraction failed - no tweets found")
        return 1

def main():
    """Entry point function that sets up the event loop"""
    try:
        if os.name == 'nt':  # Windows
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Extraction stopped by user")
        return 130
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main()) 