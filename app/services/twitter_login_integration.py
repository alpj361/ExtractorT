#!/usr/bin/env python3
"""
Twitter Login Integration Module

This module integrates the automatic login functionality with the 
TwitterPlaywrightScraper class to provide more reliable authentication.
"""

import os
import sys
import logging
import asyncio
from pathlib import Path

# Add root directory to path to ensure imports work properly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# Import login module
from twitter_login import get_storage_state, perform_login, is_storage_valid, STORAGE_PATH

# Configure logging
logger = logging.getLogger(__name__)

async def ensure_login():
    """
    Ensure a valid Twitter login session exists
    
    Returns:
        str: Path to the storage state file or None if login failed
    """
    if not is_storage_valid():
        logger.info("No valid login session found, performing login")
        success = await perform_login()
        if not success:
            logger.error("Failed to log in to Twitter")
            return None
    
    return str(STORAGE_PATH)

async def initialize_with_login(scraper):
    """
    Initialize the TwitterPlaywrightScraper with a valid login session
    
    Args:
        scraper: The TwitterPlaywrightScraper instance
        
    Returns:
        bool: True if initialization was successful
    """
    storage_path = await ensure_login()
    if not storage_path:
        logger.error("Failed to get storage state")
        return False
    
    # Store the storage path in the scraper's storage_paths
    if storage_path not in scraper.storage_paths:
        scraper.storage_paths.insert(0, storage_path)
    
    logger.info(f"Using storage state from: {storage_path}")
    return True

def patch_twitter_scraper():
    """
    Patch the TwitterPlaywrightScraper class to use our login functionality
    """
    from app.services.twitter_playwright import TwitterPlaywrightScraper
    
    # Store the original __aenter__ method
    original_aenter = TwitterPlaywrightScraper.__aenter__
    
    # Create a new __aenter__ method that uses our login
    async def patched_aenter(self):
        """Enhanced __aenter__ that ensures login is valid"""
        # First run the original method
        result = await original_aenter(self)
        
        # After initializing, if we detect login issues, use our login mechanism
        try:
            # Verify if authentication is working
            auth_ok = await self.verify_auth(retries=1)
            
            if not auth_ok:
                logger.info("Authentication not valid, using enhanced login")
                
                # Get a valid storage state
                storage_path = await ensure_login()
                if storage_path:
                    # Load the new storage state
                    await self.context.storage_state(path=storage_path)
                    logger.info("Enhanced login state loaded")
                    
                    # Verify auth again after loading new state
                    auth_ok = await self.verify_auth(retries=1)
                    if auth_ok:
                        logger.info("Enhanced login successful")
                    else:
                        logger.warning("Enhanced login did not fix authentication issues")
        except Exception as e:
            logger.error(f"Error in enhanced login: {str(e)}")
        
        return result
    
    # Replace the original method with our patched version
    TwitterPlaywrightScraper.__aenter__ = patched_aenter
    logger.info("TwitterPlaywrightScraper patched with enhanced login")

async def test_login_integration():
    """Test the login integration with TwitterPlaywrightScraper"""
    from app.services.twitter_playwright import TwitterPlaywrightScraper
    
    # Ensure the enhanced login is set up
    patch_twitter_scraper()
    
    # Create a scraper instance
    scraper = TwitterPlaywrightScraper(bypass_login=True)
    
    try:
        # Initialize with context manager
        async with scraper:
            # Check if authentication works
            auth_ok = await scraper.verify_auth()
            if auth_ok:
                logger.info("Login integration test passed: Authentication successful")
                # Try to access a user's tweets
                df = await scraper.extract_by_user("TwitterDev", max_tweets=5, min_tweets=1, max_scrolls=3)
                if df is not None and not df.empty:
                    logger.info(f"Successfully extracted {len(df)} tweets, integration works!")
                else:
                    logger.warning("Authentication successful but tweet extraction failed")
            else:
                logger.error("Login integration test failed: Authentication failed")
    except Exception as e:
        logger.error(f"Error in login integration test: {str(e)}")
        return False
    
    return auth_ok

if __name__ == "__main__":
    # Configure logging for standalone testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    # Test the integration
    asyncio.run(test_login_integration()) 