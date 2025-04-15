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

def _generate_user_data_dir():
    """Generate a unique user data directory path."""
    import uuid
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    base_dir = "/tmp/chrome-data" if os.environ.get("DOCKER_ENVIRONMENT") else "/tmp"
    return os.path.join(base_dir, f"chrome_user_data_{timestamp}_{unique_id}")

def setup_browser():
    """
    Set up a headless Chrome browser for scraping.
    
    Returns:
        tuple: (webdriver.Chrome, str) - Configured Chrome webdriver instance and user data directory path
    """
    logger.info("Setting up headless Chrome browser")
    
    # Generate unique user data directory
    user_data_dir = _generate_user_data_dir()
    os.makedirs(user_data_dir, exist_ok=True)
    logger.info(f"Created user data directory: {user_data_dir}")
    
    # Configure Chrome options for stealthy manual login
    chrome_options = Options()
    
    # Basic setup
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
    
    # Use environment variables for Chrome and ChromeDriver paths
    chrome_options.binary_location = os.environ.get('CHROME_BIN', '/usr/bin/chromium')
    chromedriver_path = os.environ.get('CHROMEDRIVER_PATH', '/usr/bin/chromedriver')
    
    # Only use headless in production
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("DOCKER_ENVIRONMENT"):
        chrome_options.add_argument("--headless=new")  # New headless mode
    
    # Modern Chrome user agent
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    # Additional stealth settings
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    chrome_options.add_argument("--disable-site-isolation-trials")
    
    # Enable all needed features for login
    prefs = {
        "credentials_enable_service": True,
        "profile.password_manager_enabled": True,
        "profile.default_content_setting_values.notifications": 2,  # Block notifications
        "profile.default_content_settings.popups": 0,  # Allow popups
        "profile.default_content_setting_values.automatic_downloads": 1,
        "profile.default_content_setting_values.plugins": 1,
        "profile.default_content_setting_values.geolocation": 2,
        "profile.managed_default_content_settings.images": 1,
        "profile.default_content_setting_values.cookies": 1
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    # Disable automation flags
    chrome_options.add_experimental_option("excludeSwitches", [
        "enable-automation",
        "enable-logging"
    ])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    
    # Use webdriver-manager in all environments
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from webdriver_manager.core.os_manager import ChromeType
        
        # Add additional options for containerized environment
        if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("DOCKER_ENVIRONMENT"):
            logger.info("Running in container environment")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--remote-debugging-port=9222")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-infobars")
            chrome_options.add_argument("--disable-notifications")
            
            # Get Chromium version for logging
            import subprocess
            try:
                chrome_version_output = subprocess.check_output([chrome_options.binary_location, "--version"]).decode().strip()
                logger.info(f"Installed Chromium: {chrome_version_output}")
            except Exception as e:
                logger.warning(f"Could not determine Chromium version: {str(e)}")
        
        # Use the ChromeDriver path from environment variable or fallback to ChromeDriverManager
        if os.path.exists(chromedriver_path):
            logger.info(f"Using ChromeDriver from: {chromedriver_path}")
            driver_path = chromedriver_path
        else:
            logger.info("Using ChromeDriverManager to get appropriate ChromeDriver")
            driver_path = ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
        logger.info(f"ChromeDriver path: {driver_path}")
        
        # Create service with the driver path
        service = Service(executable_path=driver_path)
        
        # Create driver
        driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("Chrome driver created successfully")
        
        # Log Chrome and ChromeDriver versions for debugging
        try:
            chrome_version = driver.capabilities.get('browserVersion', 'unknown')
            chromedriver_version = driver.capabilities.get('chrome', {}).get('chromedriverVersion', 'unknown')
            if isinstance(chromedriver_version, str) and ' ' in chromedriver_version:
                chromedriver_version = chromedriver_version.split(' ')[0]
            
            logger.info(f"Chrome version: {chrome_version}")
            logger.info(f"ChromeDriver version: {chromedriver_version}")
        except Exception as version_err:
            logger.warning(f"Could not determine browser versions: {str(version_err)}")
            
    except Exception as e:
        logger.error(f"Error setting up ChromeDriverManager: {str(e)}")
        
        # Fallback 1: Try with explicit path
        try:
            logger.info("Fallback 1: Trying with explicit ChromeDriver path")
            if os.path.exists(chromedriver_path):
                logger.info(f"ChromeDriver found at: {chromedriver_path}")
                service = Service(executable_path=chromedriver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("Chrome driver created with explicit path")
            else:
                raise FileNotFoundError(f"ChromeDriver not found at {chromedriver_path}")
        except Exception as fallback_err:
            logger.error(f"Fallback 1 failed: {str(fallback_err)}")
            
            # Fallback 2: Try with minimal options
            try:
                logger.info("Fallback 2: Trying with minimal options")
                minimal_options = Options()
                minimal_options.add_argument("--headless")
                minimal_options.add_argument("--no-sandbox")
                minimal_options.add_argument("--disable-dev-shm-usage")
                minimal_options.binary_location = chrome_options.binary_location
                driver = webdriver.Chrome(service=Service(chromedriver_path), options=minimal_options)
                logger.info("Chrome driver created with minimal options")
            except Exception as minimal_err:
                logger.error(f"Fallback 2 failed: {str(minimal_err)}")
                
                # Fallback 3: Last resort, try without any customization
                logger.info("Fallback 3: Last resort attempt")
                driver = webdriver.Chrome()
                logger.info("Chrome driver created with default settings")
    
    # Set page load timeout
    driver.set_page_load_timeout(30)
    
    return driver, user_data_dir

def cleanup_user_data_dir(user_data_dir):
    """Clean up Chrome user data directory."""
    import shutil
    try:
        if os.path.exists(user_data_dir):
            logger.info(f"Cleaning up user data directory: {user_data_dir}")
            shutil.rmtree(user_data_dir)
    except Exception as e:
        logger.error(f"Error cleaning up user data directory: {str(e)}")

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
