FROM python:3.12-slim

WORKDIR /app

# Copy only requirements first to leverage Docker cache
COPY pyproject.toml .

# Install build dependencies
RUN pip install --no-cache-dir hatchling

# Install project dependencies
RUN pip install --no-cache-dir .

# Copy source code
COPY src/ src/

# Expose WebSocket port
EXPOSE 8000

CMD ["python", "src/main.py"] 