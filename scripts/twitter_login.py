#!/usr/bin/env python3
"""
Twitter Login Automation with Playwright

This script automates the Twitter login process and saves the session state for future use.
It uses environment variables for credentials and implements various techniques to avoid detection.
"""

import os
import sys
import asyncio
import logging
import random
import time
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Cambiado a DEBUG para ver más información
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("twitter_login")

# Common user agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

# Storage state file
STORAGE_PATH = Path("./twitter_storage_state.json")
# Maximum age of storage state in seconds (1 day)
STORAGE_MAX_AGE = 86400

def random_delay(min_ms=100, max_ms=500):
    """Add a random delay between actions to seem more human-like"""
    delay = random.uniform(min_ms, max_ms)
    time.sleep(delay / 1000)  # Convert to seconds

def is_storage_valid():
    """Check if the storage state file exists and is not too old"""
    if not STORAGE_PATH.exists():
        return False
    
    # Check file age
    file_age = time.time() - os.path.getmtime(STORAGE_PATH)
    if file_age > STORAGE_MAX_AGE:
        logger.info(f"Storage state is too old ({file_age / 3600:.1f} hours), will refresh")
        return False
    
    return True

async def human_like_type(page, selector, text):
    """Type text in a human-like fashion with random delays between keystrokes"""
    logger.debug(f"Clicking on selector: {selector}")
    await page.click(selector)
    random_delay(200, 500)
    
    logger.debug(f"Typing text: {text}")
    # Type slower for more reliability
    for char in text:
        await page.type(selector, char, delay=random.randint(100, 200))
        random_delay(50, 150)
    
    # Verify text was entered correctly
    try:
        value = await page.evaluate(f'document.querySelector("{selector}").value')
        logger.debug(f"Entered text value: {value}")
    except:
        logger.debug("Could not verify text input value")

async def perform_login(headless=None):
    """
    Perform the Twitter login process using Playwright
    
    Args:
        headless (bool, optional): Whether to run in headless mode. If None, will use environment variable or interactive mode.
    """
    # Force reload environment variables
    load_dotenv(override=True)
    
    # Get credentials directly with fallback
    twitter_username = os.environ.get("TWITTER_USERNAME")
    twitter_password = os.environ.get("TWITTER_PASSWORD")
    
    # Debug output
    logger.debug(f"Loaded username from env: {twitter_username}")
    logger.debug(f"Password loaded: {'Yes' if twitter_password else 'No'}")
    
    if not twitter_username or not twitter_password:
        logger.error("Twitter credentials not found in .env file")
        logger.error("Please create a .env file with TWITTER_USERNAME and TWITTER_PASSWORD")
        return False
    
    # Check if we already have a valid storage state
    if is_storage_valid():
        logger.info("Using existing storage state")
        return True
    
    # Determine headless mode based on environment and parameters
    if headless is None:
        # Auto-detect: headless in Docker/CI environments, interactive otherwise
        headless = bool(os.environ.get("DOCKER_ENVIRONMENT") or 
                       os.environ.get("CI") or 
                       os.environ.get("HEADLESS_MODE"))
    
    logger.info(f"Starting Twitter login process in {'headless' if headless else 'interactive'} mode")
    
    # For testing, always use interactive mode
    headless = False
    logger.info("Forcing interactive mode for better debug visibility")
    
    async with async_playwright() as p:
        # Select a random user agent
        user_agent = random.choice(USER_AGENTS)
        logger.info(f"Using user agent: {user_agent}")
        
        # Launch browser with custom settings
        browser = await p.chromium.launch(
            headless=headless,
            slow_mo=100,  # Increased for better visibility
        )
        
        # Create a context with specific settings to avoid detection
        context = await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1366, "height": 768},
            screen={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
            permissions=["geolocation", "notifications"],
            accept_downloads=True,
        )
        
        # Create a new page
        page = await context.new_page()
        
        try:
            # Go to Twitter login page
            logger.debug("Navigating to Twitter login page")
            await page.goto("https://twitter.com/i/flow/login", wait_until="networkidle")
            logger.info("Loaded Twitter login page")
            
            # Take screenshot for debugging
            await page.screenshot(path="login_page.png")
            logger.debug("Login page screenshot saved as login_page.png")
            
            # Wait for the username field with increased timeout
            username_selector = 'input[autocomplete="username"]'
            logger.debug(f"Waiting for username field with selector: {username_selector}")
            
            try:
                await page.wait_for_selector(username_selector, timeout=15000)
                logger.info("Username field found")
            except PlaywrightTimeoutError:
                logger.error("Username field not found within timeout")
                await page.screenshot(path="username_field_not_found.png")
                logger.debug("Current page screenshot saved")
                
                # Try alternative selector
                username_selector = 'input[name="text"]'
                logger.debug(f"Trying alternative username selector: {username_selector}")
                await page.wait_for_selector(username_selector, timeout=10000)
            
            random_delay(1000, 1500)
            
            # Enter username
            logger.info(f"Entering username: {twitter_username}")
            await human_like_type(page, username_selector, twitter_username)
            random_delay(800, 1200)
            
            # Click the Next button
            next_button = 'div[role="button"]:has-text("Next")'
            logger.debug(f"Clicking next button: {next_button}")
            
            try:
                await page.click(next_button)
                logger.info("Clicked Next button")
            except:
                logger.error("Could not click Next button, trying alternative method")
                await page.screenshot(path="next_button_error.png")
                
                # Alternative: press Enter key
                await page.keyboard.press("Enter")
                logger.info("Pressed Enter key as alternative")
            
            random_delay(1500, 2500)
            
            # Save screenshot after clicking Next
            await page.screenshot(path="after_username.png")
            logger.debug("After username screenshot saved")
            
            # Handle unusual activity check if it appears
            try:
                verify_selector = 'input[data-testid="ocfEnterTextTextInput"]'
                if await page.is_visible(verify_selector, timeout=5000):
                    logger.warning("Unusual activity check detected")
                    
                    if headless:
                        logger.error("Unusual activity check detected in headless mode. Cannot proceed.")
                        return False
                    else:
                        logger.info("Please complete the verification manually...")
                        # Wait for manual verification
                        await page.pause()
            except PlaywrightTimeoutError:
                logger.info("No unusual activity check detected")
            
            # Wait for password field with increased timeout
            password_selector = 'input[type="password"]'
            logger.debug(f"Waiting for password field: {password_selector}")
            
            try:
                await page.wait_for_selector(password_selector, timeout=15000)
                logger.info("Password field found")
            except PlaywrightTimeoutError:
                logger.error("Password field not found")
                await page.screenshot(path="password_field_not_found.png")
                logger.debug("Current page screenshot saved")
                return False
            
            random_delay(1000, 1500)
            
            # Enter password
            logger.info("Entering password")
            await human_like_type(page, password_selector, twitter_password)
            random_delay(1000, 1500)
            
            # Take screenshot before login
            await page.screenshot(path="before_login.png")
            
            # Click the Login button
            login_button = 'div[data-testid="LoginForm_Login_Button"]'
            logger.debug(f"Clicking login button: {login_button}")
            
            try:
                await page.click(login_button)
                logger.info("Clicked Login button")
            except:
                logger.error("Could not click Login button, trying alternative method")
                await page.screenshot(path="login_button_error.png")
                
                # Alternative: press Enter key
                await page.keyboard.press("Enter")
                logger.info("Pressed Enter key to submit login")
            
            # Wait for successful login
            logger.info("Waiting for successful login")
            try:
                # Wait for timeline to load, indicating successful login
                await page.wait_for_selector('div[data-testid="primaryColumn"]', timeout=20000)
                logger.info("Successfully logged in to Twitter")
                
                # Save the storage state for future use
                logger.info("Saving browser state")
                await context.storage_state(path=str(STORAGE_PATH))
                
                # Take successful login screenshot
                await page.screenshot(path="login_success.png")
                logger.debug("Login success screenshot saved")
                
                # Wait a bit more to ensure everything is loaded
                random_delay(2000, 3000)
                success = True
                
            except PlaywrightTimeoutError:
                # Take error screenshot
                await page.screenshot(path="login_verification.png")
                logger.debug("Login verification screenshot saved")
                
                # Check if there's a CAPTCHA or verification challenge
                if await page.is_visible('div[data-testid="OCF_CallToAction_Button"]'):
                    logger.warning("CAPTCHA or verification detected")
                    
                    if headless:
                        logger.error("CAPTCHA detected in headless mode. Cannot proceed.")
                        await page.screenshot(path="captcha_error.png")
                        logger.info("Screenshot saved as captcha_error.png")
                        return False
                    else:
                        logger.info("Please complete the verification manually...")
                        # Pause for manual intervention
                        await page.pause()
                    
                    # After manual intervention, check if we're logged in
                    try:
                        await page.wait_for_selector('div[data-testid="primaryColumn"]', timeout=10000)
                        logger.info("Successfully logged in after manual verification")
                        # Save the storage state
                        await context.storage_state(path=str(STORAGE_PATH))
                        success = True
                    except PlaywrightTimeoutError:
                        logger.error("Login failed even after manual verification")
                        success = False
                else:
                    logger.error("Login failed - unknown reason")
                    await page.screenshot(path="login_failed.png")
                    logger.info("Error screenshot saved as login_failed.png")
                    success = False
            
        except Exception as e:
            logger.error(f"Error during login: {str(e)}")
            try:
                await page.screenshot(path="login_error.png")
                logger.info("Error screenshot saved as login_error.png")
            except:
                pass
            success = False
        
        finally:
            # Before closing, pause for manual inspection if in debug mode
            if not success and not headless:
                logger.info("Login failed. Pausing for manual inspection...")
                await page.pause()
                
            # Close browser
            await browser.close()
            
        return success

async def get_storage_state():
    """
    Get the Twitter storage state, performing login if necessary
    
    Returns:
        str: Path to the storage state file, or None if login failed
    """
    if not is_storage_valid():
        login_success = await perform_login()
        if not login_success:
            return None
    
    return str(STORAGE_PATH)

async def main():
    """Main entry point"""
    # Process command line args
    force_login = False
    headless_mode = None
    
    for arg in sys.argv[1:]:
        if arg == "--force":
            force_login = True
        elif arg == "--headless":
            headless_mode = True
        elif arg == "--interactive":
            headless_mode = False
        elif arg == "--debug":
            logger.setLevel(logging.DEBUG)
    
    # Always enable DEBUG for now
    logger.setLevel(logging.DEBUG)
    
    # Force new login if requested
    if force_login and STORAGE_PATH.exists():
        os.remove(STORAGE_PATH)
        logger.info("Forcing new login (existing session removed)")
    
    # Perform login
    success = await perform_login(headless=headless_mode)
    
    if success:
        print(f"Login successful. Storage state saved to {STORAGE_PATH}")
        return 0
    else:
        print("Login failed. See logs for details.")
        return 1

if __name__ == "__main__":
    asyncio.run(main()) 