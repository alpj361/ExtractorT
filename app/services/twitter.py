import logging
import pandas as pd
import io
import time
import os
import json
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from app.utils.browser import setup_browser, random_delay, scroll_page, cleanup_user_data_dir
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class TwitterScraper:
    """Service for scraping tweets from Twitter."""
    
    def __init__(self, username=None, password=None):
        """
        Initialize TwitterScraper with optional credentials.
        
        Args:
            username (str, optional): Twitter username or email
            password (str, optional): Twitter password
        """
        self.driver = None
        self.user_data_dir = None
        self.username = username or os.environ.get('TWITTER_USERNAME')
        self.password = password or os.environ.get('TWITTER_PASSWORD')
        
        if not self.username or not self.password:
            raise ValueError("Twitter credentials not provided. Set TWITTER_USERNAME and TWITTER_PASSWORD environment variables or pass them to the constructor.")
    
    def __enter__(self):
        """Set up the browser when entering context."""
        try:
            logger.info("Initializing browser for Twitter scraping")
            self.driver, self.user_data_dir = setup_browser()
            
            # Inject anti-detection scripts
            logger.info("Injecting anti-detection scripts")
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    window.chrome = { runtime: {} };
                """
            })
            
            logger.info("Browser setup successful")
            return self
        except Exception as e:
            logger.error(f"Browser setup failed: {str(e)}")
            if self.user_data_dir:
                cleanup_user_data_dir(self.user_data_dir)
            raise
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources when exiting context."""
        try:
            if self.driver:
                logger.info("Closing browser")
                try:
                    self.driver.quit()
                except Exception as e:
                    logger.error(f"Error closing browser: {e}")
            
            if self.user_data_dir:
                cleanup_user_data_dir(self.user_data_dir)
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def login(self, max_retries=3):
        """
        Log in to Twitter using provided credentials.
        
        Args:
            max_retries (int): Maximum number of retry attempts for login
        """
        logger.info("Attempting to log in to Twitter")
        
        for attempt in range(max_retries):
            try:
                # Navigate to login page with human-like behavior
                logger.info("Navigating to login page")
                self.driver.get("https://twitter.com")
                random_delay(2, 3)  # Wait like a human would
                
                # Click login button if present
                try:
                    login_button = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href='/login']"))
                    )
                    login_button.click()
                    random_delay(1, 2)
                except TimeoutException:
                    # Already on login page or different flow
                    self.driver.get("https://twitter.com/i/flow/login")
                
                wait = WebDriverWait(self.driver, 20)
                
                # Wait for page to load and take screenshot
                random_delay(2, 4)
                self.driver.save_screenshot("/tmp/login_page.png")
                
                # Wait for and fill username field with human-like typing
                username_field = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[autocomplete='username']"))
                )
                
                # Type username with random delays between characters
                for char in self.username:
                    username_field.send_keys(char)
                    time.sleep(random.uniform(0.1, 0.3))
                
                random_delay(0.5, 1)  # Pause before hitting enter
                username_field.send_keys(Keys.RETURN)
                logger.info("Username entered")
                
                # Add delay to simulate human behavior
                random_delay(1.5, 2.5)
                
                # Check for unusual activity detection with shorter timeout
                unusual_activity_wait = WebDriverWait(self.driver, 3)
                try:
                    unusual_activity = unusual_activity_wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[data-testid='ocfEnterTextTextInput']"))
                    )
                    logger.warning("Unusual activity check detected")
                    self.driver.save_screenshot("/tmp/unusual_activity.png")
                    raise Exception("Twitter detected unusual activity")
                except TimeoutException:
                    pass  # No unusual activity detected, continue
                
                # Wait for and fill password field with human-like typing
                password_field = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
                )
                
                # Type password with random delays between characters
                for char in self.password:
                    password_field.send_keys(char)
                    time.sleep(random.uniform(0.1, 0.3))
                
                random_delay(0.5, 1)  # Pause before hitting enter
                password_field.send_keys(Keys.RETURN)
                logger.info("Password entered")
                
                # Add longer delay to simulate human behavior
                random_delay(2.5, 4)
                
                # Verify login success
                try:
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-testid='SideNav_NewTweet_Button']")))
                    logger.info("Successfully logged in to Twitter")
                    return
                except TimeoutException:
                    # Take screenshot for debugging
                    self.driver.save_screenshot("/tmp/login_failed.png")
                    if attempt < max_retries - 1:
                        logger.warning(f"Login verification failed, retrying... (Attempt {attempt + 1}/{max_retries})")
                        continue
                    raise Exception("Could not verify successful login")
                
            except Exception as e:
                self.driver.save_screenshot(f"/tmp/login_error_{attempt}.png")
                if attempt < max_retries - 1:
                    logger.error(f"Login attempt {attempt + 1} failed: {str(e)}")
                    time.sleep(2)  # Wait before retry
                    continue
                logger.error(f"All login attempts failed: {str(e)}")
                raise Exception(f"Failed to log in after {max_retries} attempts: {str(e)}")

    def verify_login(self):
        """Verify that we are still logged in."""
        wait = WebDriverWait(self.driver, 20)
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-testid='SideNav_NewTweet_Button']")))
            logger.info("Login status verified")
            return True
        except TimeoutException:
            logger.error("Login verification failed")
            self.driver.save_screenshot("/tmp/login_verification_failed.png")
            return False
    
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
        # Log in to Twitter
        self.login()
        
        url = f"https://twitter.com/search?q=%23{clean_hashtag}&src=typed_query&f=top"
        logger.info(f"Opening URL: {url}")
        
        try:
            # Verify login status before navigating
            if not self.verify_login():
                self.login()
            
            # Navigate to the search URL
            self.driver.get(url)
            
            # Wait for page to load
            wait = WebDriverWait(self.driver, 30)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='primaryColumn']")))
            logger.info("Search page loaded")
            
            # Scroll to load more tweets
            logger.info("Scrolling to load more tweets")
            for i in range(max_scrolls):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                random_delay(1, 3)  # Random delay between scrolls
                logger.info(f"Scroll {i+1}/{max_scrolls} completed")
                
            # Take a screenshot after scrolling
            self.driver.save_screenshot(f"/tmp/search_result_{clean_hashtag}.png")
            
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
        logger.info(f"Searching for tweets with term: {search_term}")
        tweets = []
        wait = WebDriverWait(self.driver, 20)
        try:
            # Wait for tweets to be present
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]')))
            
            # Find tweets
            tweets = self.driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
            logger.info(f"Found {len(tweets)} tweets")
            
            if len(tweets) < min_tweets:
                logger.warning(f"Found fewer tweets than expected: {len(tweets)} < {min_tweets}")
                
            # Take a screenshot for debugging
            self.driver.save_screenshot('/tmp/tweets_found.png')
            logger.info("Screenshot saved as /tmp/tweets_found.png")
            
            # Log page source for debugging
            with open('/tmp/page_source.html', 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            logger.info("Page source saved as /tmp/page_source.html")
            
        except TimeoutException:
            logger.error("Timeout while waiting for tweets to load")
            self.driver.save_screenshot('/tmp/tweets_timeout.png')
            raise Exception("Failed to load tweets")
        
        logger.info(f"Total elements found: {len(tweets)}")
        
        # Process tweets
        tweets_data = []
        processed = 0
        
        for i, tweet in enumerate(tweets[:max_tweets]):
            try:
                # Extract text and other relevant information
                text = tweet.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]').text
                username = tweet.find_element(By.CSS_SELECTOR, 'div[data-testid="User-Name"]').text
                timestamp = tweet.find_element(By.CSS_SELECTOR, 'time').get_attribute('datetime')
                
                logger.debug(f"Raw tweet text: {text[:100]}...")  # Log first 100 characters
                
                # Filter by search term if provided
                if search_term is None or search_term.lower() in text.lower() or f"#{search_term.lower()}" in text.lower():
                    tweets_data.append({
                        'texto': text,
                        'usuario': username,
                        'timestamp': timestamp,
                        'numero': i+1
                    })
                    processed += 1
                    logger.debug(f"Tweet {i+1} processed")
                    
                    # Stop if we have enough tweets
                    if processed >= min_tweets and len(tweets_data) >= min_tweets:
                        logger.info(f"Reached minimum of {min_tweets} tweets, stopping")
                        break
                
                # Add a random delay between processing tweets
                random_delay(0.5, 1.5)
                        
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
