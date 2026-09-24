# Perchance Solver - Byparr/Camoufox Turnstile Solver

**Separate service for Render Account 2 (512MB) - Keeps main MCP under 120MB**

This is the **custom fork Byparr-style solver** for Perchance sitekey `0x4AAAAAAAA8g8NphwaSOT59`.

## What it does

- Uses **Camoufox** (Firefox-based stealth browser, same as Byparr) - 200MB vs 400MB+ Chromium, C++ fingerprint patches, passes CreepJS
- Solves Turnstile via `turnstile.render('#cfTurnstileCtn', {sitekey: '0x4AAAAAAAA8g8NphwaSOT59'})`
- Calls `GET /api/verifyUser?browserId=32hex&token=...&thread=0` → `userKey` 64 hex (valid 30s, IP-bound)
- Generates image via `curl_cffi` (TLS impersonation, no browser, same IP as solve) → returns base64
- **FlareSolverr-compatible API** at `/v1` for drop-in replacement

## Endpoints

- `GET /` - info
- `GET /ping`, `/healthz`, `/health` - lightweight health (no browser) - use for Render healthCheckPath
- `POST /solve` - Solve Turnstile, return `{userKey, browserId, expires_in}`
- `POST /generate` - Full flow: ad code (curl_cffi) + Turnstile (Camoufox) + generate (curl_cffi) + download → `{imageBase64, dataUrl, seed, imageId}`
- `POST /v1` - FlareSolverr-compatible: `{"cmd":"request.get","url":"https://...","maxTimeout":60000}` → `{solution: {cookies, userAgent, response}}`

## Deploy to Render Account 2 (separate workspace)

1. Push this folder to GitHub `perchance-solver`
2. Render → New → Web Service → Connect repo
3. Runtime: Docker, Dockerfile: `./Dockerfile`, Port: 8000
4. Env: `PORT=8000`, `HOST=0.0.0.0`, `PYTHONUNBUFFERED=1`
5. Health Check Path: `/ping`
6. Plan: Free (512MB, 0.1 CPU, 750h) - fits because Camoufox ~250MB vs SeleniumBase 800MB
7. URL: `https://perchance-solver.onrender.com`

Keep alive (Render sleeps after 15 min):
- UptimeRobot free → Monitor `https://perchance-solver.onrender.com/ping` every 5 min
- Or cron-job.org every 14 min

## How Main MCP Lite uses it

Main MCP (Render Account 1, 120MB, no browser) sets env `SOLVER_URL=https://perchance-solver.onrender.com`

```python
# In perchance-mcp-lite
import httpx
resp = httpx.post(f"{SOLVER_URL}/generate", json={"prompt": "cosmic fear garou", "resolution": "768x768"}, timeout=120).json()
# resp["imageBase64"] → save to file
```

No browser on main MCP → stays 120MB, fits 512MB.

## Why Byparr/Camoufox over FlareSolverr?

- FlareSolverr official v3.5.2 fixed Turnstile in #1634 but still Chromium + undetected-chromedriver = 400MB+ and detectable
- Byparr uses Camoufox Firefox - patches fingerprints in C++ not JS, 0% detection on CreepJS, BrowserScan, 200MB
- Benchmarks 2026: Byparr top open-source for Turnstile success rate

## Docker Images (if you want generic solver, not custom)

- Byparr: `ghcr.io/thephaseless/byparr:latest` - drop-in FlareSolverr replacement, same API
- FlareSolverr: `ghcr.io/flaresolverr/flaresolverr:v3.5.2`
- turnstile-solver: `ghcr.io/icemellow-me/turnstile-solver` - pure token solver

But for Perchance, custom solver returning userKey + image is more reliable than generic FlareSolverr HTML.

## Test

```bash
curl https://perchance-solver.onrender.com/ping
# → {"status":"ok"}

curl -X POST https://perchance-solver.onrender.com/solve -H "Content-Type: application/json" -d '{}'
# → {"status":"success","userKey":"abc...","browserId":"...","expires_in":30}

curl -X POST https://perchance-solver.onrender.com/generate -H "Content-Type: application/json" -d '{"prompt":"a cute cat","resolution":"512x512"}'
# → {"status":"success","imageBase64":"...","fileSize":12345}
```
