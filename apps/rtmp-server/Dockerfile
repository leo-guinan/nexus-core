FROM python:3.12-slim

# Install FFmpeg and other dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements first to leverage Docker cache
COPY pyproject.toml .

# Install build dependencies
RUN pip install --no-cache-dir hatchling

# Install project dependencies
RUN pip install --no-cache-dir .

# Copy source code
COPY src/ src/

# Expose RTMP port
EXPOSE 1935

CMD ["python", "src/main.py"] 