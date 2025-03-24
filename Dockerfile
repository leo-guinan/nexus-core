FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy lock files
COPY uv.lock pyproject.toml ./

# Install dependencies using uv
RUN uv pip install --no-cache --system .

COPY . .

EXPOSE 1935

CMD ["python", "main.py"]