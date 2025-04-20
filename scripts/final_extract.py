#!/usr/bin/env python3
"""
Comprehensive Tweet Extraction Script with Automatic Login

This script extracts recent tweets from specified Twitter users using the 
TwitterPlaywrightScraper scraper with enhanced login functionality. 
It prioritizes real-time tweets and properly filters out pinned and promoted tweets.

It can be run in both local and Docker environments.
"""

import os
import sys
import logging
import asyncio
import pandas as pd
from datetime import datetime
import traceback
import argparse
import importlib.util

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("final_extract")

# Make sure temp directory exists
os.makedirs("/tmp", exist_ok=True)

# Create output directory
script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, "output")
os.makedirs(output_dir, exist_ok=True)

# Check if login integration module exists
login_integration_path = os.path.join(script_dir, "app/services/twitter_login_integration.py")
has_login_integration = os.path.exists(login_integration_path)

def is_docker():
    """Check if running inside a Docker container"""
    return os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENVIRONMENT') == '1'

def setup_login_integration():
    """Set up the login integration if available"""
    if has_login_integration:
        try:
            # Import the module
            spec = importlib.util.spec_from_file_location("twitter_login_integration", login_integration_path)
            login_integration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(login_integration)
            
            # Patch the TwitterPlaywrightScraper to use enhanced login
            login_integration.patch_twitter_scraper()
            logger.info("Login integration successfully set up")
            return True
        except Exception as e:
            logger.error(f"Error setting up login integration: {str(e)}")
    
    return False

async def extract_tweets(username, max_tweets=15, min_tweets=5, max_scrolls=5):
    """
    Extract tweets from the specified user profile, prioritizing recent tweets.
    
    Args:
        username (str): Twitter username to extract tweets from
        max_tweets (int): Maximum number of tweets to extract
        min_tweets (int): Minimum number of tweets to extract
        max_scrolls (int): Maximum number of scrolls to perform
        
    Returns:
        DataFrame: Pandas DataFrame containing extracted tweets
    """
    try:
        # Import locally to avoid early initialization issues
        from app.services.twitter_playwright import TwitterPlaywrightScraper
        
        # Set up login integration if available
        integration_active = setup_login_integration()
        
        logger.info(f"Starting tweet extraction for user: {username}")
        logger.info(f"Parameters: max_tweets={max_tweets}, min_tweets={min_tweets}, max_scrolls={max_scrolls}")
        logger.info(f"Enhanced login integration: {'Active' if integration_active else 'Not available'}")
        
        # Create Twitter scraper instance
        twitter_scraper = TwitterPlaywrightScraper(bypass_login=True)
        
        try:
            # Use the context manager to handle setup and cleanup
            async with twitter_scraper:
                # Explicitly set Docker environment if needed
                if is_docker():
                    logger.info("Running in Docker environment")
                    os.environ["DOCKER_ENVIRONMENT"] = "1"
                
                # Extract tweets with search-first approach for recent tweets
                logger.info(f"Extracting tweets for @{username}")
                tweets_df = await twitter_scraper.extract_by_user(
                    username=username,
                    max_tweets=max_tweets,
                    min_tweets=min_tweets,
                    max_scrolls=max_scrolls
                )
                
                # Check if tweets were extracted
                if tweets_df is not None and not tweets_df.empty:
                    tweet_count = len(tweets_df)
                    logger.info(f"Successfully extracted {tweet_count} tweets")
                    
                    # Sort tweets by timestamp (most recent first)
                    if 'timestamp' in tweets_df.columns:
                        tweets_df = tweets_df.sort_values(by='timestamp', ascending=False)
                        logger.info("Tweets sorted by timestamp (most recent first)")
                    
                    return tweets_df
                else:
                    logger.warning(f"No tweets were extracted for @{username}")
                    return pd.DataFrame()
                    
        except Exception as e:
            logger.error(f"Error during tweet extraction: {str(e)}")
            logger.error(traceback.format_exc())
            raise
            
    except Exception as e:
        logger.error(f"Fatal error in extract_tweets: {str(e)}")
        logger.error(traceback.format_exc())
        return pd.DataFrame()

async def extract_tweets_api(username, count=15, min_tweets=5):
    """
    Fallback function to extract tweets using the API method.
    
    Args:
        username (str): Twitter username to extract tweets from
        count (int): Number of tweets to extract
        min_tweets (int): Minimum number of tweets required
        
    Returns:
        DataFrame: Pandas DataFrame containing extracted tweets
    """
    try:
        # Try to import Twikit - this is optional, as we'll install it if needed
        try:
            import twikit
        except ImportError:
            logger.info("Twikit not found. Attempting to install...")
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "twikit"])
            import twikit
            
        # Direct implementation using Twikit
        logger.info(f"Starting API tweet extraction for user: {username}")
        
        from twikit import Client
        
        try:
            client = Client()
            
            # Get user details
            user = await client.get_user_by_screen_name(username)
            logger.info(f"User found: {user.name} (@{user.screen_name})")
            
            # Extract tweets
            logger.info(f"Extracting up to {count} tweets via API...")
            tweets = await user.get_tweets('Tweets', count=count)
            
            # Process tweets
            tweets_data = []
            pinned_tweet_id = None
            
            # Check for pinned tweet
            if hasattr(user, 'pinned_tweet_id') and user.pinned_tweet_id:
                pinned_tweet_id = user.pinned_tweet_id
                logger.info(f"Pinned tweet detected with ID: {pinned_tweet_id}")
            
            # Process each tweet
            for i, tweet in enumerate(tweets):
                # Skip pinned tweets
                if pinned_tweet_id and str(tweet.id) == str(pinned_tweet_id):
                    logger.info(f"Skipping pinned tweet: {tweet.full_text[:50]}...")
                    continue
                
                # Get readable date
                fecha = tweet.created_at.strftime('%Y-%m-%d %H:%M:%S') if hasattr(tweet, 'created_at') else 'Unknown'
                
                tweet_data = {
                    'texto': tweet.full_text,
                    'usuario': tweet.user.screen_name,
                    'timestamp': tweet.created_at,
                    'numero': i + 1,
                    'retweets': tweet.retweet_count,
                    'favoritos': tweet.favorite_count,
                    'id': tweet.id,
                    'url': f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}"
                }
                
                tweets_data.append(tweet_data)
                logger.info(f"Tweet {i+1} processed ({fecha}): {tweet.full_text[:50]}...")
            
            # Create DataFrame
            if tweets_data:
                df = pd.DataFrame(tweets_data)
                # Sort by timestamp from newest to oldest
                df = df.sort_values(by='timestamp', ascending=False)
                logger.info(f"API extraction successful: {len(df)} tweets for @{username}")
                return df
            else:
                logger.warning(f"No tweets found for @{username} via API")
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"Error in API extraction: {str(e)}")
            return pd.DataFrame()
            
    except Exception as e:
        logger.error(f"API extraction failed: {str(e)}")
        logger.error(traceback.format_exc())
        return pd.DataFrame()

def save_results(tweets_df, username, output_file=None):
    """Save extraction results to CSV file and display summary"""
    if tweets_df.empty:
        logger.warning("No tweets to save")
        return None
        
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(output_dir, f"{username}_{timestamp}.csv")
    
    # Save to CSV
    tweets_df.to_csv(output_file, index=False)
    logger.info(f"Results saved to {output_file}")
    
    # Create a more accessible copy in the current directory
    local_copy = f"{username}_latest.csv"
    tweets_df.to_csv(local_copy, index=False)
    logger.info(f"Local copy saved as {local_copy}")
    
    # Display summary
    print(f"\nExtracted {len(tweets_df)} tweets from @{username}")
    print(f"Results saved to: {output_file} and {local_copy}")
    
    # Display recent tweets summary
    if len(tweets_df) > 0:
        sample_size = min(5, len(tweets_df))
        print(f"\nMost recent {sample_size} tweets:")
        for i, (_, row) in enumerate(tweets_df.head(sample_size).iterrows()):
            timestamp = row.get('timestamp', 'Unknown date')
            text = row.get('texto', '')[:100] + ('...' if len(row.get('texto', '')) > 100 else '')
            print(f"{i+1}. [{timestamp}] {text}")
    
    return output_file

async def main_async():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Extract recent tweets from Twitter users")
    parser.add_argument("username", help="Twitter username to extract tweets from (without @)")
    parser.add_argument("--max", "-m", type=int, default=15, help="Maximum number of tweets to extract")
    parser.add_argument("--min", type=int, default=5, help="Minimum number of tweets required")
    parser.add_argument("--scrolls", "-s", type=int, default=5, help="Maximum number of scrolls to perform")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug logging")
    
    # Handle direct command line args or parsed args
    if len(sys.argv) > 1 and "--" not in sys.argv[1]:
        # Simple positional args mode
        username = sys.argv[1].strip('@')
        max_tweets = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        min_tweets = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        max_scrolls = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    else:
        # Parse with argparse
        args = parser.parse_args()
        username = args.username.strip('@')
        max_tweets = args.max
        min_tweets = args.min
        max_scrolls = args.scrolls
        
        # Set debug logging if requested
        if args.debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Debug logging enabled")
    
    logger.info(f"Starting extraction process for user @{username}")
    
    try:
        # First try with Playwright
        tweets_df = await extract_tweets(username, max_tweets, min_tweets, max_scrolls)
        
        # If Playwright method fails or returns too few results, try API method
        if tweets_df.empty or len(tweets_df) < min_tweets:
            logger.info(f"Playwright extraction returned insufficient results ({len(tweets_df) if not tweets_df.empty else 0} tweets). Trying API method...")
            api_tweets_df = await extract_tweets_api(username, max_tweets, min_tweets)
            
            if not api_tweets_df.empty and (tweets_df.empty or len(api_tweets_df) > len(tweets_df)):
                logger.info(f"Using API results with {len(api_tweets_df)} tweets instead of Playwright results")
                tweets_df = api_tweets_df
        
        # Save results
        if not tweets_df.empty:
            save_results(tweets_df, username)
            return 0
        else:
            logger.error(f"Failed to extract tweets for @{username} using both methods")
            print(f"No tweets could be extracted for @{username}")
            return 1
    
    except Exception as e:
        logger.error(f"Extraction failed: {str(e)}")
        logger.error(traceback.format_exc())
        print(f"Error: {str(e)}")
        return 1

def main():
    """Main entry point with proper event loop handling"""
    try:
        if sys.platform == 'win32':
            # Windows specific event loop policy
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        # Use the running event loop if available, otherwise create a new one
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        return loop.run_until_complete(main_async())
    except Exception as e:
        logger.error(f"Fatal error in main: {str(e)}")
        logger.error(traceback.format_exc())
        print(f"Fatal error: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 