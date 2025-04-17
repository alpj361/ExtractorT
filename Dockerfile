FROM --platform=linux/amd64 python:3.11-bullseye

# Create a directory for the cookies file
RUN mkdir -p /app/cookies

# Set working directory
WORKDIR /app

# Install dependencies for Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
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
    libglib2.0-0 \
    libnss3-tools \
    libxss1 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libxtst6 \
    libpango-1.0-0 \
    libcairo2 \
    xvfb \
    jq \
    # Additional dependencies
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxshmfence1 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

# Install a specific version of Chrome
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get update && \
    apt-get install -y ./google-chrome-stable_current_amd64.deb && \
    rm google-chrome-stable_current_amd64.deb && \
    rm -rf /var/lib/apt/lists/*

# Install matching ChromeDriver
RUN CHROME_VERSION=$(google-chrome-stable --version | awk '{print $3}' | awk -F. '{print $1"."$2"."$3"."$4}') && \
    echo "Detected Chrome version: $CHROME_VERSION" && \
    # Get the closest matching ChromeDriver version available
    CHROMEDRIVER_VERSION=$(curl -s https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json | jq -r --arg ver "$CHROME_VERSION" '.versions[] | select(.version | startswith($ver)) | .version' | sort -V | tail -n 1) && \
    # Fallback to latest stable if specific version not found
    if [ -z "$CHROMEDRIVER_VERSION" ]; then \
        echo "Specific ChromeDriver version for $CHROME_VERSION not found, fetching latest stable..."; \
        LATEST_STABLE_VERSION=$(curl -s https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions.json | jq -r '.channels.Stable.version'); \
        CHROMEDRIVER_VERSION=$LATEST_STABLE_VERSION; \
    fi && \
    echo "Using ChromeDriver version: $CHROMEDRIVER_VERSION" && \
    CHROMEDRIVER_URL=$(curl -s https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json | jq -r --arg ver "$CHROMEDRIVER_VERSION" '.versions[] | select(.version == $ver) | .downloads.chromedriver[] | select(.platform == "linux64") | .url') && \
    echo "Downloading ChromeDriver from: $CHROMEDRIVER_URL" && \
    wget -q -O chromedriver_linux64.zip $CHROMEDRIVER_URL && \
    unzip chromedriver_linux64.zip && \
    mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
    rm -rf chromedriver_linux64.zip chromedriver-linux64 && \
    chmod +x /usr/local/bin/chromedriver

# Set up Chrome options
ENV CHROME_BIN=/usr/bin/google-chrome-stable
ENV CHROME_PATH=/usr/bin/google-chrome-stable
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
ENV CHROME_OPTS="--no-sandbox --disable-dev-shm-usage --disable-gpu --remote-debugging-port=9222"

# Create directory for Chrome profile with proper permissions
RUN mkdir -p /chrome_profile && \
    chmod -R 777 /chrome_profile

# Set up display for headless mode
ENV DISPLAY=:99

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

# Note: We don't copy the chrome_profile directory here since it will be mounted as a volume

# Make sure permissions are set correctly for the ChromeDriver
RUN chmod -R 777 /usr/local/bin/chromedriver

# Create a script to start Xvfb and then run the application with debug info
RUN echo '#!/bin/bash\n\
echo "Starting container with the following environment:"\n\
echo "DOCKER_ENVIRONMENT=$DOCKER_ENVIRONMENT"\n\
echo "Checking Chrome profile directory:"\n\
ls -la /chrome_profile\n\
if [ -d "/chrome_profile/Default" ]; then\n\
  echo "Default directory exists:"\n\
  ls -la /chrome_profile/Default | grep -E "Cookies|Login"\n\
else\n\
  echo "WARNING: Default directory does not exist in Chrome profile"\n\
fi\n\
echo "Starting Xvfb..."\n\
Xvfb :99 -screen 0 1920x1080x24 -ac &\n\
sleep 2\n\
echo "Testing Chrome installation..."\n\
google-chrome-stable --version\n\
echo "Testing Chromedriver installation..."\n\
chromedriver --version\n\
echo "Starting application server..."\n\
uvicorn app.main:app --host 0.0.0.0 --port ${PORT}' > /app/start.sh && \
    chmod +x /app/start.sh

# Command to run the application
CMD ["/app/start.sh"]
