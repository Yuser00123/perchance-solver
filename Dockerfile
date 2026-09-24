# Perchance Solver - Python Slim + Camoufox ONLY - 300MB - No SeleniumBase - Fixes OOM 502 and pip not found
# Use this if Byparr image fails - python:3.11-slim has pip and is reliable on Render

FROM python:3.11-slim

# Install system deps for Firefox (Camoufox) + curl
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libatspi2.0-0 \
    libasound2 \
    libcups2 \
    libdrm2 \
    libxdamage1 \
    libxkbcommon0 \
    libxcomposite1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libgtk-3-0 \
    libxfixes3 \
    libxext6 \
    libx11-6 \
    libglib2.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libgraphene-1.0-0 \
    libepoxy0 \
    libx11-xcb1 \
    libxcb1 \
    libxcb-shm0 \
    libxcb-dri2-0 \
    libxcb-dri3-0 \
    libxcb-glx0 \
    libxcb-present0 \
    libxcb-sync1 \
    libxcb-xfixes0 \
    libxtst6 \
    libxshmfence1 \
    libwayland-client0 \
    libwayland-cursor0 \
    libwayland-egl1 \
    libcloudproviders0 \
    libcolord2 \
    libdconf1 \
    libpolkit-gobject-1-0 \
    fonts-liberation \
    libappindicator3-1 \
    xdg-utils \
    xvfb \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Camoufox browser (Firefox stealth, same as Byparr) - 200MB
RUN camoufox fetch || python -m camoufox fetch || echo "Camoufox fetch failed, continuing but may need manual fetch"

COPY . .

RUN mkdir -p /app/perchance-output /home/user/.perchance-solver /tmp/debs/out/usr/lib/x86_64-linux-gnu && \
    chmod -R 777 /app /home/user/.perchance-solver || true

ENV PYTHONUNBUFFERED=1
ENV LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
ENV PORT=8000
ENV HOST=0.0.0.0

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/cron || exit 1

CMD ["sh", "-c", "python -m uvicorn solver:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 75 --log-level info"]
