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

# Install ChromeDriver matching the Chrome version - using a more robust approach
RUN apt-get update && apt-get install -y wget unzip curl \
    && export PATH=$PATH:/usr/bin \
    && which google-chrome-stable \
    && CHROME_MAJOR_VERSION=$(google-chrome-stable --version | awk '{print $3}' | cut -d '.' -f 1) \
    && echo "Detected Chrome major version: $CHROME_MAJOR_VERSION" \
    && wget -q -O - https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_MAJOR_VERSION} > /tmp/chromedriver_version.txt \
    && CHROMEDRIVER_VERSION=$(cat /tmp/chromedriver_version.txt) \
    && echo "Using ChromeDriver version: $CHROMEDRIVER_VERSION" \
    && wget -q -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip \
    && unzip -q /tmp/chromedriver.zip -d /usr/local/bin/ \
    && rm /tmp/chromedriver.zip /tmp/chromedriver_version.txt \
    && chmod +x /usr/local/bin/chromedriver \
    && ls -la /usr/local/bin/chromedriver \
    && echo "ChromeDriver installation completed"

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
