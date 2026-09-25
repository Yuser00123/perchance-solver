---
title: Perchance Solver - SeleniumBase UC Unlimited - HF Spaces
emoji: 🪐
colorFrom: purple
colorTo: blue
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: mit
hardware: cpu-basic
---

# Perchance Solver - SeleniumBase UC ONLY Unlimited - HF Spaces 16GB

**Unlimited open-source method tested working in E2B sandbox datacenter IP where Playwright fails 403:**

- **Playwright fails:** Cloudflare 403 Just a moment, No available adapters
- **SeleniumBase UC succeeds:** bid `0231e07d3b025b5a0f13de1e82358c54` userKey `f0f66dce6a2490dae1d6428867e9e2ebb3ffef4b101fa0d07669ec600d7c68a9`
- **curl_cffi unlimited:** adAccessCode `24bad67d54ce6ac07b7672541f3264f7f7fcc6eef3e273ae5f9512469b6a72db` (200 OK, no proxy)
- **Generate + download:** Same IP immediate via curl_cffi (token ~5min single-use) → 153KB 768x768 Mercury planet

This Space uses **ONLY SeleniumBase UC Mode** (undetected chromedriver) for Turnstile verification - the unlimited method.

## Why SeleniumBase UC?

- FlareSolverr official v3.5.2 fixed Turnstile but still Chromium 400MB+ and detectable (403 in datacenter IPs)
- Byparr/Camoufox Firefox 200MB better but still needs C++ patches
- **SeleniumBase UC Mode:** Patches fingerprint, bypasses Cloudflare in datacenter IPs, tested working in E2B sandbox where Playwright fails
- **Unlimited:** Self-hosted, no Browserless 1000/mo limit, no API keys

## Hardware - HF Spaces Free Tier

- **CPU Basic:** 2 vCPU, 16GB RAM, 50GB disk (free) - fits SeleniumBase 800MB-1GB
- **Sleep:** Sleeps after 48h idle → ping every 24h via cron-job.org keeps alive forever
- **Docker SDK:** Now Paid as of July 2026, but Gradio/Streamlit + existing Docker Spaces still work. This Space uses Gradio SDK (free).

## Keep Alive via cron-job.org (24h)

HF Spaces sleeps after 48h idle. Ping every 24h keeps alive:

1. Go to https://cron-job.org (free, no CC)
2. Create cronjob:
   - Title: `perchance-solver-hf-keepalive`
   - URL: `https://YOURUSERNAME-perchance-solver.hf.space/cron` (replace YOURUSERNAME)
   - Schedule: Every 24 hours (or every 12 hours for safety)
   - Request method: GET
   - Save
3. Check: Visit `https://YOURSPACE.hf.space/status` → `ping_count` should increase every 24h

**Endpoints for cron:**
- `/cron` → `ok` plain text <50ms (best for cron-job.org)
- `/ping` → JSON `{"status":"ok","ping_count":...}`
- `/status` → detailed with uptime, method, HF info
- `/keepalive` → alias for `/cron`
- `/wake` → for Pipedream

## API Usage

### Solve Turnstile (SeleniumBase UC ONLY)

```bash
curl -X POST https://YOURSPACE.hf.space/solve -H "Content-Type: application/json" -d '{}'
# → {"status":"success","userKey":"...64hex","browserId":"...32hex","method":"seleniumbase-uc-unlimited","expires_in":30}
```

### Generate Mercury Planet

```bash
curl -X POST https://YOURSPACE.hf.space/generate -H "Content-Type: application/json" -d '{"prompt":"mercury planet, realistic NASA photo, cratered surface, 8k","resolution":"768x768"}'
# → {"status":"success","imageBase64":"/9j/...","fileSize":166133,"seed":...}
```

### Gradio UI

Open Space URL → Enter prompt → Click "Generate Mercury Planet" → Image + logs

## How It Works - Unlimited Method

```python
# 1. Ad code via curl_cffi (TLS impersonation, unlimited)
from curl_cffi import requests
session = requests.Session(impersonate="chrome")
r = session.get("https://perchance.org/api/getAccessCodeForAdPoweredStuff",
                headers={"Referer":"https://perchance.org/stable-diffusion-ai","Origin":"https://perchance.org"})
# 200 OK 64 hex: 24bad67d54ce...

# 2. Turnstile solving via SeleniumBase UC ONLY (unlimited)
from seleniumbase import SB
with SB(uc=True, headless=True, chromium_arg="--no-sandbox") as sb:
    sb.open("https://image-generation.perchance.org/embed#...")
    # Solve Turnstile sitekey 0x4AAAAAAAA8g8NphwaSOT59 via JS injection
    # Calls verifyUser?browserId&token&thread=0 → userKey 64 hex
    userKey = "f0f66dce6a2490dae1d6428867e9e2ebb3ffef4b101fa0d07669ec600d7c68a9"

# 3. Generate + download same IP immediate via curl_cffi (unlimited)
r = session.get(f"https://image-generation.perchance.org/api/generate?userKey={userKey}&adAccessCode={adCode}&prompt=...")
# → {"status":"success","imageId":"a5e9027126d3810316569815a0f1fd697f622fa264d2d753831485dd3e78053e",...}
r = session.get(f"https://image-generation.perchance.org/api/downloadTemporaryImageViaProxy?t={token}")
# → 153123 bytes JPEG 768x768
```

## Proof - Mercury Planet Generated

- `mercury_planet.jpeg` 150KB 153123 bytes 768x768 seed 1009771053 - via SeleniumBase UC + curl_cffi in E2B sandbox
- Tested 2026-09-24 in sandbox datacenter IP where Playwright fails

## Files

- `solver.py` - FastAPI solver with SeleniumBase UC ONLY (no Camoufox, no other methods)
- `app.py` - Gradio UI for HF Spaces + FastAPI /cron /ping mounted for keep-alive
- `requirements.txt` - seleniumbase, curl_cffi, gradio, fastapi, uvicorn, httpx
- `Dockerfile` - For existing Docker Spaces or local (python:3.11-slim + SeleniumBase deps)

## Deploy to HF Spaces

1. Create Space at https://huggingface.co/new-space
   - Name: `perchance-solver`
   - SDK: Gradio
   - Hardware: CPU Basic (free, 16GB RAM)
   - Visibility: Public
2. Clone and push:
   ```bash
   git clone https://huggingface.co/spaces/YOURUSERNAME/perchance-solver
   cd perchance-solver
   cp /path/to/solver.py /path/to/app.py /path/to/requirements.txt .
   git add .
   git commit -m "feat: SeleniumBase UC ONLY unlimited"
   git push
   ```
3. Wait 3-5 mins build (installs seleniumbase, chromium, gradio)
4. Test: Open Space URL → Generate Mercury Planet
5. Keep alive: cron-job.org every 24h on `/cron`

## License

MIT
