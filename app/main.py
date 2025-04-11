from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
import io
import logging
from app.routes import extract

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Twitter Scraper API",
    description="API for extracting tweets by hashtag/topic or user",
    version="1.0.0",
)

# Include routers
app.include_router(extract.router)

@app.get("/")
async def root():
    """Root endpoint to check if the API is running."""
    return {"message": "Twitter Scraper API is running", "status": "ok"}

@app.get("/health")
async def health():
    """Health check endpoint for Railway."""
    return {"status": "healthy"}
