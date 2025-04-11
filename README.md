# Twitter Scraper Microservice

A microservice for extracting tweets by hashtag/topic or user, built for deployment on Railway.

## Features

- Extract tweets by hashtag or topic
- Extract tweets from a user's timeline
- Return results as CSV files
- Headless browser operation for containerized environments
- Anti-detection measures (user agent rotation, random delays)

## API Endpoints

### Extract by Hashtag

```
GET /extract/hashtag/{hashtag}
```

Parameters:
- `hashtag`: Hashtag to search for (with or without the # symbol)
- `max_tweets` (optional): Maximum number of tweets to extract (default: 30)
- `min_tweets` (optional): Minimum number of tweets to extract before stopping (default: 10)
- `max_scrolls` (optional): Maximum number of page scrolls (default: 10)

Example:
```
GET /extract/hashtag/BecasPorNuestroFuturo?max_tweets=20&min_tweets=5
```

### Extract by User

```
GET /extract/user/{username}
```

Parameters:
- `username`: Twitter username (with or without the @ symbol)
- `max_tweets` (optional): Maximum number of tweets to extract (default: 30)
- `min_tweets` (optional): Minimum number of tweets to extract before stopping (default: 10)
- `max_scrolls` (optional): Maximum number of page scrolls (default: 10)

Example:
```
GET /extract/user/elonmusk?max_tweets=20&min_tweets=5
```

## Local Development

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the development server:
   ```
   uvicorn app.main:app --reload
   ```
4. Access the API documentation at http://localhost:8000/docs

## Deployment on Railway

1. Create a new project on [Railway](https://railway.app/)
2. Connect your GitHub repository
3. Railway will automatically detect the Dockerfile and deploy the service
4. Access your deployed API at the provided Railway URL

## Environment Variables

- `PORT`: Port to run the server on (default: 8000)
- `RAILWAY_ENVIRONMENT`: Set to any value when running on Railway
- `DOCKER_ENVIRONMENT`: Set to any value when running in Docker

## Notes

- This service uses web scraping techniques which may break if Twitter changes its UI
- Twitter may rate limit or block requests if too many are made in a short period
- The service is designed for on-demand use, not continuous scraping
