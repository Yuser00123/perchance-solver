# Perchance Solver - Byparr Docker Image Directly - 200MB Fixed OOM 502 - FIXED pip not found
# Byparr image uses pip3 / python3 -m pip, not pip

FROM ghcr.io/thephaseless/byparr:latest

USER root

# Install curl for healthcheck
RUN apt-get update && apt-get install -y \
    curl \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements (NO seleniumbase, only camoufox + fastapi + curl_cffi)
COPY requirements.txt .

# FIX: Byparr image has pip3 not pip - try all variants
RUN pip3 install --no-cache-dir -r requirements.txt || \
    python3 -m pip install --no-cache-dir -r requirements.txt || \
    python -m pip install --no-cache-dir -r requirements.txt || \
    pip install --no-cache-dir -r requirements.txt

# Ensure Camoufox browser is fetched - Byparr image should already have it
RUN python3 -m camoufox fetch || python -m camoufox fetch || echo "Camoufox fetch skipped, using Byparr's pre-installed browser"

# Copy our custom solver (Camoufox ONLY, no SeleniumBase fallback)
COPY . .

# Clean up and setup perms
RUN rm -rf /tmp/* /var/tmp/* && \
    mkdir -p /app/perchance-output /home/user/.perchance-solver && \
    chmod -R 777 /app /home/user/.perchance-solver || true

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV HOST=0.0.0.0
ENV BYPARR_BROWSER=camoufox
ENV CAMOUFOX_HEADLESS=true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/cron || exit 1

CMD ["sh", "-c", "python3 -m uvicorn solver:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 75 --log-level info || python -m uvicorn solver:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 75 --log-level info"]
