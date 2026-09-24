# Perchance Solver - Byparr Docker Image Directly - 200MB Fixed OOM 502
# Removes SeleniumBase fallback (800MB) that caused OOM on Render 512MB Free Tier
# Uses ghcr.io/thephaseless/byparr:latest - 200MB vs 400MB official FlareSolverr
# Camoufox Firefox stealth - C++ fingerprint patches, 0% detection, best for Turnstile

FROM ghcr.io/thephaseless/byparr:latest

# Byparr image is based on Python + Camoufox pre-installed, but we need to install our custom deps
# Switch to root to install system deps if needed
USER root

# Install curl for healthcheck and python deps
RUN apt-get update && apt-get install -y \
    curl \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements (NO seleniumbase, only camoufox + fastapi + curl_cffi)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure Camoufox browser is fetched - Byparr image should already have it, but fetch again to be safe
# This downloads Firefox ~150MB, but Byparr image already includes it
RUN python -m camoufox fetch || echo "Camoufox fetch skipped, using Byparr's pre-installed browser"

# Copy our custom solver (Camoufox ONLY, no SeleniumBase fallback)
COPY . .

# Clean up unnecessary files to save space
RUN rm -rf /tmp/* /var/tmp/* && \
    mkdir -p /app/perchance-output /home/user/.perchance-solver /tmp/debs/out/usr/lib/x86_64-linux-gnu && \
    chmod -R 777 /app /home/user/.perchance-solver

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV HOST=0.0.0.0
# Byparr env vars (optional, for compatibility)
ENV BYPARR_BROWSER=camoufox
ENV CAMOUFOX_HEADLESS=true

EXPOSE 8000

# Healthcheck uses lightweight /cron (no browser) - 50ms plain text, best for Render + cron-job.org 30s timeout
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/cron || exit 1

# Override Byparr's default CMD with our solver
CMD ["sh", "-c", "python -m uvicorn solver:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 75 --log-level info"]
