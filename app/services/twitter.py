import logging
import pandas as pd
import io
import time
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from app.utils.browser import setup_browser, random_delay, scroll_page

logger = logging.getLogger(__name__)

class TwitterScraper:
    """Service for scraping tweets from Twitter."""
    
    def __init__(self):
        self.driver = None
    
   def __enter__(self):
    """Set up the browser when entering context."""
    try:
        self.driver = setup_browser()
        return self
    except Exception as e:
        logger.error(f"Browser setup failed: {str(e)}")
        # Include more detailed diagnostic information
        import sys
        import platform
        logger.error(f"Python version: {sys.version}")
        logger.error(f"Platform: {platform.platform()}")
        # Check Chrome installation
        import subprocess
        try:
            chrome_version = subprocess.check_output(["google-chrome", "--version"]).decode().strip()
            logger.info(f"Chrome version: {chrome_version}")
        except:
            logger.error("Could not detect Chrome version")
        raise
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources when exiting context."""
        if self.driver:
            logger.info("Closing browser")
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
    
    def extract_by_hashtag(self, hashtag, max_tweets=30, min_tweets=10, max_scrolls=10):
        """
        Extract tweets containing a specific hashtag.
        
        Args:
            hashtag (str): Hashtag to search for (without the # symbol)
            max_tweets (int): Maximum number of tweets to extract
            min_tweets (int): Minimum number of tweets to extract before stopping
            max_scrolls (int): Maximum number of page scrolls
            
        Returns:
            pandas.DataFrame: DataFrame containing extracted tweets
        """
        logger.info(f"Extracting tweets for hashtag: #{hashtag}")
        
        # Clean hashtag (remove # if present)
        clean_hashtag = hashtag.strip()
        if clean_hashtag.startswith("#"):
            clean_hashtag = clean_hashtag[1:]
        
        # Construct search URL
        url = f"https://twitter.com/search?q=%23{clean_hashtag}&src=typed_query&f=top"
        logger.info(f"Opening URL: {url}")
        
        try:
            # Navigate to the search URL
            self.driver.get(url)
            
            # Wait for page to load
            random_delay(5, 7)
            
            # Scroll to load more tweets
            logger.info("Scrolling to load more tweets")
            scroll_page(self.driver, num_scrolls=max_scrolls)
            
            # Find tweets using multiple selectors
            tweets_data = self._find_and_process_tweets(clean_hashtag, max_tweets, min_tweets)
            
            # Create DataFrame
            if tweets_data:
                df = pd.DataFrame(tweets_data)
                logger.info(f"Successfully extracted {len(df)} tweets for #{clean_hashtag}")
                return df
            else:
                logger.warning(f"No tweets found for #{clean_hashtag}")
                return pd.DataFrame(columns=["texto", "numero"])
                
        except TimeoutException:
            logger.error("Timeout while loading Twitter page")
            raise Exception("Timeout while loading Twitter page")
        except WebDriverException as e:
            logger.error(f"WebDriver error: {str(e)}")
            raise Exception(f"Browser error: {str(e)}")
        except Exception as e:
            logger.error(f"Error extracting tweets: {str(e)}")
            raise Exception(f"Failed to extract tweets: {str(e)}")
    
    def extract_by_user(self, username, max_tweets=30, min_tweets=10, max_scrolls=10):
        """
        Extract tweets from a specific user's timeline.
        
        Args:
            username (str): Twitter username (without the @ symbol)
            max_tweets (int): Maximum number of tweets to extract
            min_tweets (int): Minimum number of tweets to extract before stopping
            max_scrolls (int): Maximum number of page scrolls
            
        Returns:
            pandas.DataFrame: DataFrame containing extracted tweets
        """
        logger.info(f"Extracting tweets for user: @{username}")
        
        # Clean username (remove @ if present)
        clean_username = username.strip()
        if clean_username.startswith("@"):
            clean_username = clean_username[1:]
        
        # Construct profile URL
        url = f"https://twitter.com/{clean_username}"
        logger.info(f"Opening URL: {url}")
        
        try:
            # Navigate to the profile URL
            self.driver.get(url)
            
            # Wait for page to load
            random_delay(5, 7)
            
            # Scroll to load more tweets
            logger.info("Scrolling to load more tweets")
            scroll_page(self.driver, num_scrolls=max_scrolls)
            
            # Find tweets (no filtering by hashtag for user timeline)
            tweets_data = self._find_and_process_tweets(None, max_tweets, min_tweets)
            
            # Create DataFrame
            if tweets_data:
                df = pd.DataFrame(tweets_data)
                logger.info(f"Successfully extracted {len(df)} tweets for @{clean_username}")
                return df
            else:
                logger.warning(f"No tweets found for @{clean_username}")
                return pd.DataFrame(columns=["texto", "numero"])
                
        except TimeoutException:
            logger.error("Timeout while loading Twitter page")
            raise Exception("Timeout while loading Twitter page")
        except WebDriverException as e:
            logger.error(f"WebDriver error: {str(e)}")
            raise Exception(f"Browser error: {str(e)}")
        except Exception as e:
            logger.error(f"Error extracting tweets: {str(e)}")
            raise Exception(f"Failed to extract tweets: {str(e)}")
    
    def _find_and_process_tweets(self, search_term, max_tweets, min_tweets):
        """
        Find and process tweets from the current page.
        
        Args:
            search_term (str): Term to filter tweets by (None for no filtering)
            max_tweets (int): Maximum number of tweets to extract
            min_tweets (int): Minimum number of tweets to extract before stopping
            
        Returns:
            list: List of dictionaries containing tweet data
        """
        tweets = []
        
        # Method 1: Find tweets using article elements
        articles = self.driver.find_elements(By.XPATH, '//article[@data-testid="tweet"]')
        if articles:
            logger.info(f"Found {len(articles)} tweets using article selector")
            tweets = articles
        
        # Method 2: Alternative selector if Method 1 fails
        if len(tweets) < min_tweets:
            logger.info("Trying alternative selector")
            cells = self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="cellInnerDiv"]')
            if cells:
                logger.info(f"Found {len(cells)} elements using alternative selector")
                tweets = cells
        
        # Method 3: Last resort selector
        if len(tweets) < min_tweets:
            logger.info("Trying timeline selector")
            timeline = self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="primaryColumn"] > div > div > div > div')
            if timeline and len(timeline) > 4:
                logger.info(f"Found {len(timeline)} elements in timeline")
                tweets = timeline[4:]  # Skip header elements
        
        logger.info(f"Total elements found: {len(tweets)}")
        
        # Process tweets
        tweets_data = []
        processed = 0
        
        for i, tweet in enumerate(tweets[:max_tweets]):
            try:
                # Extract text
                text = tweet.text
                
                # Filter by search term if provided
                if search_term is None or search_term.lower() in text.lower() or f"#{search_term.lower()}" in text.lower():
                    tweets_data.append({
                        'texto': text,
                        'numero': i+1
                    })
                    processed += 1
                    logger.debug(f"Tweet {i+1} processed")
                    
                    # Stop if we have enough tweets
                    if processed >= min_tweets and len(tweets_data) >= min_tweets:
                        logger.info(f"Reached minimum of {min_tweets} tweets, stopping")
                        break
                        
            except Exception as e:
                logger.error(f"Error processing tweet {i+1}: {str(e)}")
        
        return tweets_data
    
    def dataframe_to_csv(self, df):
        """
        Convert DataFrame to CSV string.
        
        Args:
            df (pandas.DataFrame): DataFrame to convert
            
        Returns:
            str: CSV string
        """
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        return csv_buffer.getvalue()
