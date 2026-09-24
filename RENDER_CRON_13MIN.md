# cron-job.org Every 13 Minutes - Both Services

**Both components can be called every 13 minutes by cron-job.org - Code edited accordingly**

## Why 13 Minutes?

- Render Free sleeps after **15 min idle**
- 13 < 15, so ping every 13 min keeps alive forever
- 750h/month free per workspace, 720h used if 24/7, under limit
- cron-job.org free timeout **30s**, Render cold start **30-60s** → first morning ping may timeout, second succeeds
- Fix: Use `/cron` (plain text `ok` in <50ms, safest) + Pipedream at 07:50 on `/wake` (no timeout) for morning wake-up

## Code Edits for cron-job.org (Done)

### Both Services Now Have:

**1. Ultra-lightweight `/cron` endpoint (BEST FOR cron-job.org):**
```python
@app.get("/cron")
@app.head("/cron")
async def cron_endpoint():
    PING_COUNT["count"] += 1
    return PlainTextResponse("ok", headers={"Cache-Control": "no-cache"})
```
- Returns plain text `ok` in **<50ms**, no browser, no JSON, no heavy import
- Handles both GET and HEAD (UptimeRobot uses HEAD)
- `Cache-Control: no-cache` prevents caching
- **Use this URL for cron-job.org**

**2. `/ping` with source detection and no-cache:**
```python
@app.get("/ping")
async def health_check(request: Request):
    ua = request.headers.get("user-agent","").lower()
    source = "cron-job.org" if "cron-job.org" in ua else "uptimerobot" if "uptimerobot" in ua else "unknown"
    return JSONResponse(
        {"status":"ok","source":source,"ping_count":...},
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )
```
- Returns JSON in <100ms, no browser
- Detects `cron-job.org` vs `uptimerobot` vs `render-health` via User-Agent
- Tracks `ping_count`, `last_cron`, `last_ua`

**3. `/wake` for Pipedream morning wake-up:**
```python
@app.get("/wake")
async def wake_endpoint():
    # Returns ok immediately (<50ms) but Render starts warming up
    return {"status":"ok","message":"woke"}
```
- Pipedream has **no 30s timeout**, handles 50s cold start
- Schedule Pipedream at 07:50 daily on `/wake`, then cron-job.org every 13 min 08:00-23:59

**4. `/status` with cron monitoring:**
- Shows `uptime`, `ping_count`, `last_cron`, `last_source`, `last_user_agent`
- For lite, also checks solver health via `SOLVER_URL/ping`

**5. Docker HEALTHCHECK uses `/cron`:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/cron || exit 1
```
- Even lighter than `/ping`

### Files Edited:

- `/perchance-mcp-lite/remote_server.py` - Added `/cron`, `/keepalive`, `/wake`, `/status`, HEAD support, no-cache headers, ping tracking, cron source detection
- `/perchance-solver/solver.py` - Same: `/cron`, `/keepalive`, `/wake`, `/status`, HEAD, no-cache, tracking
- Both Dockerfiles - HEALTHCHECK now uses `/cron` (50ms) not `/ping`
- `docker-compose.split.yml` - healthcheck uses `/cron`

## Setup cron-job.org for Both Services

### Job 1 - Lite MCP (Render Account 1)

- URL: `https://perchance-mcp-lite.onrender.com/cron` (or `/ping` for JSON)
- Schedule: Every 13 minutes
- Method: GET
- Title: `perchance-lite-keepalive`

### Job 2 - Solver (Render Account 2, Byparr/Camoufox)

- URL: `https://perchance-solver.onrender.com/cron` (or `/ping`)
- Schedule: Every 13 minutes
- Method: GET
- Title: `perchance-solver-keepalive`

### Total Hours

- 1 service: 60/13 * 24 * 31 = ~3432 pings/month, 720h instance time
- 2 services: 2 × 720h = 1440h, but each workspace has 750h free, so 720h per workspace < 750h, OK
- Each account separate, so each gets 750h

### Pipedream Morning Wake-up (Fixes 30s Timeout)

1. Pipedream.com → New Workflow → Schedule → `0 50 7 * * *` (07:50 UTC daily)
2. HTTP GET `https://perchance-mcp-lite.onrender.com/wake`
3. HTTP GET `https://perchance-solver.onrender.com/wake`
4. Deploy

Pipedream has no 30s timeout, handles 50s cold start, wakes at 07:50, then cron-job.org every 13 min keeps alive.

**Alternative (better): UptimeRobot every 5 min on `/ping` - no 30s timeout issue**

## Test

```bash
curl https://perchance-mcp-lite.onrender.com/cron
# → ok

curl https://perchance-mcp-lite.onrender.com/ping
# → {"status":"ok","source":"unknown","ping_count":1}

curl -H "User-Agent: cron-job.org" https://perchance-mcp-lite.onrender.com/ping
# → {"status":"ok","source":"cron-job.org",...}

curl https://perchance-mcp-lite.onrender.com/status
# → {"service":"perchance-mcp-lite","uptime_human":"2h 13m","ping_count":10,"last_source":"cron-job.org",...}

# Same for solver
curl https://perchance-solver.onrender.com/cron
# → ok
```

After setup, `/status` should show `ping_count` increasing every 13 min and `last_source: cron-job.org`.
