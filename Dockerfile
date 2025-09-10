FROM python:3.10-slim

# Install system dependencies needed for Playwright Chromium
RUN apt-get update && apt-get install -y \
    wget gnupg curl unzip \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libxkbcommon0 libx11-xcb1 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libasound2 libpangocairo-1.0-0 \
    libpango-1.0-0 libxshmfence1 libxext6 libxfixes3 \
    fonts-unifont fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser binaries (without deps)
RUN playwright install chromium

# Copy project files
COPY . /app

# Expose Render port
ENV PORT=10000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
