FROM python:3.9-slim

# Create a directory for the cookies file
RUN mkdir -p /app/cookies

# Set working directory
WORKDIR /app

# Install Chromium and dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    curl \
    unzip \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*


# Set up Chromium options
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROME_PATH=/usr/lib/chromium/
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV CHROME_OPTS="--no-sandbox --disable-dev-shm-usage --disable-gpu --remote-debugging-port=9222"

# Create parent directory for Chrome user data
RUN mkdir -p /tmp/chrome-data && chmod 777 /tmp/chrome-data


# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DOCKER_ENVIRONMENT=1
ENV PORT=8000

# Expose port
EXPOSE ${PORT}

# Copy the cookies file
COPY twitter_cookies.json /app/cookies/twitter_cookies.json

# Command to run the application
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
