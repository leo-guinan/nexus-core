FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy lock files
COPY uv.lock pyproject.toml ./

# Install dependencies using uv
RUN uv pip install --no-cache --system .

COPY . .

EXPOSE 1935 8000

# The GLADIA_API_KEY will be passed as a build arg or environment variable
ENV GLADIA_API_KEY=${GLADIA_API_KEY}
ENV WEBHOOK_URL=http://localhost:8000/webhook

# Create a script to run both servers
RUN echo '#!/bin/sh\n\
uvicorn webhook_server:app --host 0.0.0.0 --port 8000 & \n\
python main.py' > /app/start.sh && \
    chmod +x /app/start.sh

CMD ["/app/start.sh"]