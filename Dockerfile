# ─────────────────────────────────────────────────────────────────────────────
#  Gas Booking System  |  Dockerfile
#  Multi-stage optimized build — Python 3.11 slim
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose internal Flask port
EXPOSE 5002

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5002/api/health')" || exit 1

# Start the application via startup script
CMD ["bash", "start.sh"]
