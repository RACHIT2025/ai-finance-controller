FROM python:3.11-slim

WORKDIR /app

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and assets
COPY . .

# Expose default port
EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0

# Start Uvicorn dynamically binding to $PORT provided by cloud host (default 8000)
CMD ["sh", "-c", "uvicorn fincontroller.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]

