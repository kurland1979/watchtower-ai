# =============================================================================
# WatchTower AI — Multi-Stage Dockerfile
#
# Stage 1 (builder): Install Python dependencies in a venv
# Stage 2 (runtime): Copy only the venv + app code (smaller image)
#
# Build:   docker build -t watchtower-ai .
# Run:     docker run --env-file .env watchtower-ai
# =============================================================================

# --- Stage 1: Builder ---
FROM python:3.12-slim AS builder

WORKDIR /build

# Install system deps needed for building wheels (e.g., gcc for some pip packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (Docker layer caching — avoids re-installing
# all deps when only code changes)
COPY requirements.txt .

# Create virtual environment and install deps
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# --- Stage 2: Runtime ---
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install Playwright browser (only needed if JS scraping is enabled)
# Comment out these lines if you don't use js_render=true
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy venv from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Playwright browsers
RUN playwright install chromium 2>/dev/null || true

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p /app/logs

# Don't run as root in production
RUN useradd --create-home appuser && \
    chown -R appuser:appuser /app
USER appuser

# Health check — hits the dashboard API health endpoint
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')" || exit 1

# Default: run the scheduler (main agent loop)
# Override with: docker run watchtower-ai python wsgi.py  (for dashboard only)
CMD ["python", "main.py"]
