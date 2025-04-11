#!/usr/bin/env python3
"""
Script to run the Twitter Scraper API locally for testing.
"""
import uvicorn
import logging

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)
    
    logger.info("Starting Twitter Scraper API locally")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
