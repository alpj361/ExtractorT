#!/usr/bin/env python3
"""
Script to test the browser setup for the Twitter Scraper.
This script attempts to initialize the browser and navigate to a test page.
"""
import logging
import os
import sys
from app.utils.browser import setup_browser, cleanup_user_data_dir

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def test_browser():
    """Test the browser setup and navigation."""
    logger.info("Testing browser setup")
    
    # Para pruebas locales en macOS, no usamos el entorno Docker
    if sys.platform == "darwin":  # macOS
        if "DOCKER_ENVIRONMENT" in os.environ:
            del os.environ["DOCKER_ENVIRONMENT"]
    
    try:
        # Setup browser
        driver, profile_dir = setup_browser()
        logger.info(f"Browser setup successful. Profile directory: {profile_dir}")
        
        # Navigate to a test page
        logger.info("Navigating to test page")
        driver.get("https://www.google.com")
        
        # Get page title
        title = driver.title
        logger.info(f"Page title: {title}")
        
        # Take a screenshot
        screenshot_path = "browser_test.png"
        driver.save_screenshot(screenshot_path)
        logger.info(f"Screenshot saved to {screenshot_path}")
        
        # Close browser
        driver.quit()
        logger.info("Browser closed successfully")
        
        return True
    except Exception as e:
        logger.error(f"Browser test failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_browser()
    if success:
        logger.info("Browser test completed successfully")
        sys.exit(0)
    else:
        logger.error("Browser test failed")
        sys.exit(1) 