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

# Install ChromeDriver compatible with Chrome 135
# Using a known working version for Chrome 135
RUN apt-get update && apt-get install -y wget unzip curl

# Install ChromeDriver 135.0.5349.0 which is compatible with Chrome 135
RUN echo "Installing ChromeDriver for Chrome 135" \
    && wget -q -O /tmp/chromedriver.zip https://storage.googleapis.com/chrome-for-testing-public/135.0.5349.0/linux64/chromedriver-linux64.zip \
    && unzip -q /tmp/chromedriver.zip -d /tmp/ \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && rm -rf /tmp/chromedriver.zip /tmp/chromedriver-linux64 \
    && chmod +x /usr/local/bin/chromedriver

# Verify installation
RUN echo "ChromeDriver installation completed" \
    && ls -la /usr/local/bin/chromedriver

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
