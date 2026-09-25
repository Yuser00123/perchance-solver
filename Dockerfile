# Perchance Solver - SeleniumBase UC ONLY Unlimited - HF Spaces 16GB + Render 1GB
# This is the UNLIMITED method tested working in E2B sandbox datacenter IP where Playwright fails 403
# Playwright: 403 Just a moment, No available adapters
# SeleniumBase UC: SUCCESS bid 0231e07d3b025b5a0f13de1e82358c54 userKey f0f66dce6a2490dae1d6428867e9e2ebb3ffef4b101fa0d07669ec600d7c68a9
# Memory: ~800MB-1GB (fits HF Spaces 16GB, Render Starter 1GB, not Render Free 512MB)

FROM python:3.11-slim

# Install system deps for Chromium (SeleniumBase UC) + curl + xvfb for headless
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
    chromium \
    chromium-driver \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright chromium for SeleniumBase to use (fallback)
RUN playwright install chromium || python -m playwright install chromium || echo "Playwright chromium install skipped"

COPY . .

RUN mkdir -p /app/perchance-output /home/user/.perchance-solver /tmp/debs/out/usr/lib/x86_64-linux-gnu && \
    chmod -R 777 /app /home/user/.perchance-solver || true

ENV PYTHONUNBUFFERED=1
ENV PORT=7860
ENV HOST=0.0.0.0
# HF Spaces requires port 7860 for Gradio
# For Render, PORT env will override to 8000 or 10000

EXPOSE 7860
EXPOSE 8000

# Healthcheck uses lightweight /cron (no browser) - 50ms plain text
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-7860}/cron || curl -f http://localhost:8000/cron || exit 1

# For HF Spaces Gradio: app.py launches Gradio on 7860 + FastAPI on 8000
# For Render: solver.py launches FastAPI on PORT
CMD ["sh", "-c", "if [ -f app.py ]; then python app.py; else python -m uvicorn solver:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 75 --log-level info; fi"]
