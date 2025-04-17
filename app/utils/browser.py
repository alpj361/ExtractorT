import logging
import os
import random
import time
import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.service import Service
import shutil
import subprocess
import nest_asyncio
import asyncio

logger = logging.getLogger(__name__)

# Configure Chrome paths
if os.environ.get("DOCKER_ENVIRONMENT"):
    profile_dir = "/chrome_profile"
    chrome_binary = "/usr/bin/google-chrome-stable"
    chromedriver_path = "/usr/local/bin/chromedriver"
    # Log environment for debugging
    logger.info(f"Running in Docker environment")
    logger.info(f"Profile directory set to: {profile_dir}")
    logger.info(f"Chrome binary path: {chrome_binary}")
    logger.info(f"ChromeDriver path: {chromedriver_path}")
else:
    def get_profile_dir():
        base_dir = os.path.join(os.path.expanduser("~"), ".chrome-profiles")
        profile = os.path.join(base_dir, "twitter-profile")
        os.makedirs(profile, exist_ok=True)
        return profile

    profile_dir = get_profile_dir()
    chrome_binary = None
    chromedriver_path = None

def setup_xvfb():
    """Set up Xvfb display for headless mode."""
    if os.environ.get("DOCKER_ENVIRONMENT"):
        try:
            # Check if Xvfb is already running
            result = subprocess.run(['pgrep', 'Xvfb'], capture_output=True, text=True)
            if not result.stdout.strip():
                subprocess.Popen(['Xvfb', ':99', '-screen', '0', '1920x1080x24', '-ac'])
                logger.info("Started Xvfb display server")
                time.sleep(2)  # Give Xvfb time to start
            else:
                logger.info("Xvfb is already running")
        except Exception as e:
            logger.error(f"Failed to start Xvfb: {str(e)}")
            raise

def setup_browser():
    """
    Set up Chrome browser with undetected-chromedriver and persistent profile.
    
    Returns:
        tuple: (uc.Chrome, str) - Configured Chrome instance and profile directory path
    """
    logger.info("Setting up Chrome browser with undetected-chromedriver")
    
    # Set up Xvfb for headless mode
    setup_xvfb()
    
    # Clean up any existing Chrome processes
    try:
        if os.environ.get("DOCKER_ENVIRONMENT"):
            logger.info("Checking for running Chrome processes...")
            subprocess.run(["pkill", "-f", "chrome"], capture_output=True)
            time.sleep(1)  # Give time for processes to terminate
    except Exception as e:
        logger.warning(f"Error cleaning up Chrome processes: {str(e)}")
    
    # Get persistent profile directory
    logger.info(f"Using Chrome profile directory: {profile_dir}")
    
    # Remove lock files that might prevent browser startup
    try:
        lock_files = ["SingletonLock", "SingletonSocket", "SingletonCookie"]
        for lock_file in lock_files:
            lock_path = os.path.join(profile_dir, lock_file)
            if os.path.exists(lock_path):
                logger.info(f"Removing lock file: {lock_path}")
                os.remove(lock_path)
    except Exception as e:
        logger.warning(f"Error removing lock files: {str(e)}")
    
    # Verify Chrome profile directory exists and is accessible
    if not os.path.exists(profile_dir):
        logger.error(f"Chrome profile directory does not exist: {profile_dir}")
        raise Exception("Chrome profile directory not found")
    
    try:
        # Create Default directory if it doesn't exist
        default_dir = os.path.join(profile_dir, "Default")
        if not os.path.exists(default_dir):
            logger.info(f"Creating Default directory in profile: {default_dir}")
            os.makedirs(default_dir, exist_ok=True)
            
        # Create Preferences file if it doesn't exist
        preferences_file = os.path.join(default_dir, "Preferences")
        if not os.path.exists(preferences_file):
            logger.info(f"Creating Preferences file: {preferences_file}")
            with open(preferences_file, 'w') as f:
                f.write('{}')
                
        # Try with undetected_chromedriver
        max_retries = 3
        retry_count = 0
        last_error = None
        
        # Check if profile exists for headless mode decision
        profile_exists = os.path.exists(os.path.join(profile_dir, "Default"))
        
        while retry_count < max_retries:
            try:
                # Configure Chrome options for undetected-chromedriver
                options = uc.ChromeOptions()
                
                # Basic Chrome arguments
                options.add_argument("--remote-debugging-port=9222")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")
                options.add_argument("--window-size=1920,1080")
                options.add_argument("--disable-extensions")
                options.add_argument("--disable-setuid-sandbox")
                options.add_argument("--disable-infobars")
                
                # Use a random profile subdirectory to avoid "already in use" errors
                if retry_count > 0:  # Only on retry attempts
                    temp_profile_dir = f"{profile_dir}_{random.randint(1000, 9999)}"
                    try:
                        if not os.path.exists(temp_profile_dir):
                            logger.info(f"Creating temporary profile at {temp_profile_dir}")
                            shutil.copytree(profile_dir, temp_profile_dir, dirs_exist_ok=True)
                        options.add_argument(f"--user-data-dir={temp_profile_dir}")
                        logger.info(f"Using temporary profile: {temp_profile_dir}")
                    except Exception as e:
                        logger.warning(f"Error creating temp profile: {str(e)}")
                        options.add_argument(f"--user-data-dir={profile_dir}")
                else:
                    options.add_argument(f"--user-data-dir={profile_dir}")
                
                options.add_argument("--disable-features=IsolateOrigins,site-per-process")
                options.add_argument("--log-level=3")  # Reduce logging
                options.add_argument("--disable-blink-features=AutomationControlled")
                
                # Set Chrome binary path if in Docker
                if os.environ.get("DOCKER_ENVIRONMENT") and chrome_binary:
                    if os.path.exists(chrome_binary):
                        options.binary_location = chrome_binary
                        logger.info(f"Set Chrome binary location to {chrome_binary}")
                
                # Only use headless in production and if profile exists
                if (os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("DOCKER_ENVIRONMENT")) and profile_exists:
                    logger.info("Using headless mode with existing profile")
                    options.add_argument("--headless=new")
                    options.add_argument("--remote-debugging-port=9222")
                    options.add_argument("--disable-software-rasterizer")
                    logger.info("*** Remote debugging enabled on port 9222 ***")
                else:
                    logger.info("Running in visible mode for manual login or debugging")
                
                # Additional settings
                prefs = {
                    "credentials_enable_service": True,
                    "profile.password_manager_enabled": True,
                    "profile.default_content_setting_values.notifications": 2,
                    "profile.default_content_settings.popups": 0,
                    "profile.default_content_setting_values.automatic_downloads": 1
                }
                options.add_experimental_option("prefs", prefs)
                
                # Create driver with undetected_chromedriver
                try:
                    driver = uc.Chrome(
                        options=options,
                        driver_executable_path=chromedriver_path,
                        browser_executable_path=chrome_binary,
                        use_subprocess=True,
                        version_main=135
                    )
                    logger.info("Chrome driver created successfully with undetected-chromedriver")
                except Exception as e:
                    logger.warning(f"Failed to create undetected_chromedriver: {str(e)}")
                    logger.info("Falling back to regular selenium webdriver")
                    
                    # Fall back to regular selenium webdriver
                    options = webdriver.ChromeOptions()
                    options.add_argument("--no-sandbox")
                    options.add_argument("--disable-dev-shm-usage")
                    options.add_argument("--disable-gpu")
                    options.add_argument("--window-size=1920,1080")
                    
                    # Add random subdir to avoid "already in use" errors
                    temp_profile_dir = f"{profile_dir}_{random.randint(1000, 9999)}"
                    try:
                        # If we got "already in use" error, copy the profile to a temporary directory
                        if not os.path.exists(temp_profile_dir):
                            logger.info(f"Creating temporary profile at {temp_profile_dir}")
                            shutil.copytree(profile_dir, temp_profile_dir, dirs_exist_ok=True)
                        options.add_argument(f"--user-data-dir={temp_profile_dir}")
                    except Exception as e:
                        logger.warning(f"Error creating temp profile, using original: {str(e)}")
                        options.add_argument(f"--user-data-dir={profile_dir}")
                    
                    options.add_argument("--disable-extensions")
                    options.add_argument("--disable-infobars")
                    options.add_argument("--disable-blink-features=AutomationControlled")
                    
                    if os.environ.get("DOCKER_ENVIRONMENT") and chrome_binary:
                        options.binary_location = chrome_binary
                    
                    if (os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("DOCKER_ENVIRONMENT")) and profile_exists:
                        options.add_argument("--headless=new")
                        options.add_argument("--remote-debugging-port=9222")
                        options.add_argument("--disable-software-rasterizer")
                        logger.info("*** Remote debugging enabled on port 9222 (fallback driver) ***")
                    
                    service = Service(executable_path=chromedriver_path)
                    driver = webdriver.Chrome(
                        service=service,
                        options=options
                    )
                    logger.info("Chrome driver created successfully with regular selenium webdriver")
                
                # Set page load timeout
                driver.set_page_load_timeout(30)
                
                # Test browser working
                driver.get("about:blank")
                logger.info("Browser test page loaded successfully")
                
                # Additional browser checks
                if not driver.current_url:
                    raise Exception("Browser initialization failed - no current URL")
                
                return driver, profile_dir
                
            except Exception as e:
                last_error = e
                retry_count += 1
                logger.warning(f"Attempt {retry_count} failed: {str(e)}")
                time.sleep(2)  # Wait before retrying
                
        logger.error(f"Failed to create Chrome driver after {max_retries} attempts. Last error: {str(last_error)}")
        raise last_error
        
    except Exception as e:
        logger.error(f"Error setting up Chrome driver: {str(e)}")
        raise

def cleanup_user_data_dir(user_data_dir):
    """Clean up Chrome user data directory."""
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

def run_async(coro):
    """
    Run an asynchronous coroutine from synchronous code.
    
    Args:
        coro: Coroutine to run
        
    Returns:
        Result of the coroutine
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # No running loop
        loop = None

    if loop and loop.is_running():
        # If there's a running loop, use it
        return asyncio.ensure_future(coro)
    else:
        # Otherwise, create a new loop
        return asyncio.run(coro)

nest_asyncio.apply()
