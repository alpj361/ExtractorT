import logging
import os
import random
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)

# List of user agents to rotate
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
]

def setup_browser():
    """
    Set up a headless Chrome browser for scraping.
    
    Returns:
        webdriver.Chrome: Configured Chrome webdriver instance
    """
    logger.info("Setting up headless Chrome browser")
    
    # Configure Chrome options for headless operation
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Explicitly set Chrome binary path in container
    chrome_options.binary_location = "/usr/bin/google-chrome-stable"
    
    # Rotate user agents to avoid detection
    user_agent = random.choice(USER_AGENTS)
    chrome_options.add_argument(f"--user-agent={user_agent}")
    
    # Disable images to improve performance
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    
    # Disable automation flags
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    
    # Check if running in Docker/Railway environment
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("DOCKER_ENVIRONMENT"):
        logger.info("Running in container environment")
        # In Docker/Railway, use Chrome without Selenium Manager
        from selenium.webdriver.chrome.service import Service
        service = Service()
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        # For local development, use ChromeDriverManager
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            logger.info("Using ChromeDriverManager for local development")
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        except Exception as e:
            logger.error(f"Error setting up ChromeDriverManager: {e}")
            # Fallback to direct Chrome driver
            driver = webdriver.Chrome(options=chrome_options)
    
    # Set page load timeout
    driver.set_page_load_timeout(30)
    
    return driver

def random_delay(min_seconds=1, max_seconds=3):
    """
    Add a random delay to avoid detection.
    
    Args:
        min_seconds (int): Minimum delay in seconds
        max_seconds (int): Maximum delay in seconds
    """
    delay = random.uniform(min_seconds, max_seconds)
    logger.debug(f"Adding random delay of {delay:.2f} seconds")
    time.sleep(delay)

def scroll_page(driver, num_scrolls=10, scroll_delay=2):
    """
    Scroll down the page to load more content.
    
    Args:
        driver (webdriver.Chrome): Chrome webdriver instance
        num_scrolls (int): Number of times to scroll
        scroll_delay (int): Delay between scrolls in seconds
    """
    logger.info(f"Scrolling page {num_scrolls} times")
    for i in range(num_scrolls):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        logger.debug(f"Scroll {i+1}/{num_scrolls}")
        # Add some randomness to the delay
        time.sleep(scroll_delay + random.uniform(0, 1))
