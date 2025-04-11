from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
import io
import logging
from app.services.twitter import TwitterScraper

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/extract",
    tags=["extract"],
    responses={404: {"description": "Not found"}},
)

@router.get("/hashtag/{hashtag}")
async def extract_by_hashtag(
    hashtag: str,
    max_tweets: int = Query(30, description="Maximum number of tweets to extract"),
    min_tweets: int = Query(10, description="Minimum number of tweets to extract before stopping"),
    max_scrolls: int = Query(10, description="Maximum number of page scrolls")
):
    """
    Extract tweets containing a specific hashtag.
    
    Args:
        hashtag: Hashtag to search for (with or without the # symbol)
        max_tweets: Maximum number of tweets to extract
        min_tweets: Minimum number of tweets to extract before stopping
        max_scrolls: Maximum number of page scrolls
        
    Returns:
        CSV file containing extracted tweets
    """
    logger.info(f"API request to extract tweets for hashtag: {hashtag}")
    
    try:
        with TwitterScraper() as scraper:
            df = scraper.extract_by_hashtag(
                hashtag=hashtag,
                max_tweets=max_tweets,
                min_tweets=min_tweets,
                max_scrolls=max_scrolls
            )
            
            # Convert DataFrame to CSV
            csv_content = scraper.dataframe_to_csv(df)
            
            # Create response with CSV file
            return StreamingResponse(
                io.StringIO(csv_content),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={hashtag.strip('#')}_tweets.csv"
                }
            )
    except Exception as e:
        logger.error(f"Error extracting tweets for hashtag {hashtag}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/user/{username}")
async def extract_by_user(
    username: str,
    max_tweets: int = Query(30, description="Maximum number of tweets to extract"),
    min_tweets: int = Query(10, description="Minimum number of tweets to extract before stopping"),
    max_scrolls: int = Query(10, description="Maximum number of page scrolls")
):
    """
    Extract tweets from a specific user's timeline.
    
    Args:
        username: Twitter username (with or without the @ symbol)
        max_tweets: Maximum number of tweets to extract
        min_tweets: Minimum number of tweets to extract before stopping
        max_scrolls: Maximum number of page scrolls
        
    Returns:
        CSV file containing extracted tweets
    """
    logger.info(f"API request to extract tweets for user: {username}")
    
    try:
        with TwitterScraper() as scraper:
            df = scraper.extract_by_user(
                username=username,
                max_tweets=max_tweets,
                min_tweets=min_tweets,
                max_scrolls=max_scrolls
            )
            
            # Convert DataFrame to CSV
            csv_content = scraper.dataframe_to_csv(df)
            
            # Create response with CSV file
            clean_username = username.strip('@')
            return StreamingResponse(
                io.StringIO(csv_content),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={clean_username}_tweets.csv"
                }
            )
    except Exception as e:
        logger.error(f"Error extracting tweets for user {username}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
