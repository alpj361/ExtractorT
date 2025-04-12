FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install Chrome and dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
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


# Install Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*


# Instalar ChromeDriver 135.0.5349.0 (compatible con Chrome 135)
RUN wget -O /tmp/chromedriver.zip https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/135.0.5349.0/linux64/chromedriver-linux64.zip && \
    unzip /tmp/chromedriver.zip -d /tmp/chromedriver && \
    mv /tmp/chromedriver/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -rf /tmp/chromedriver*


# Install tools needed for webdriver-manager
RUN apt-get update && apt-get install -y wget unzip curl

# Create cache directory for webdriver-manager
RUN mkdir -p /root/.cache/selenium \
    && chmod -R 777 /root/.cache

# Set environment variables for webdriver-manager
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
ENV WDM_LOG_LEVEL=0
ENV WDM_PROGRESS_BAR=0
ENV WDM_LOCAL=0
ENV SE_DISABLE_MANAGER=true


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

# Command to run the application
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
