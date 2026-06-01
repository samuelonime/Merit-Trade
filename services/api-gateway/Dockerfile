FROM python:3.11-slim

# Security: run as non-root
RUN groupadd -r merit && useradd -r -g merit merit

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy shared utilities first (layer cache)
COPY ../shared /app/../shared

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY . .

# Non-root execution
RUN chown -R merit:merit /app
USER merit

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
