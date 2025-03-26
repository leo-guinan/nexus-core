FROM python:3.12-slim

WORKDIR /app

# Copy only requirements first to leverage Docker cache
COPY pyproject.toml .

# Install build dependencies
RUN pip install --no-cache-dir hatchling

# Copy source code first
COPY src/ src/

# Install project dependencies and package in editable mode
RUN pip install --no-cache-dir -e .

# Copy alembic config and migrations
COPY alembic.ini alembic.ini
COPY alembic/ alembic/

# Expose WebSocket port
EXPOSE 8000

CMD ["python", "src/main.py"] 