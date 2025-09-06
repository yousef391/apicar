FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget gnupg curl unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright + dependencies
RUN pip install --no-cache-dir fastapi uvicorn[standard] playwright
RUN playwright install --with-deps

# Set workdir
WORKDIR /app

# Copy project files
COPY . /app

# Expose Render port
ENV PORT=10000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
