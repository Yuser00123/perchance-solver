# cron-job.org Setup - Both Services Every 13 Minutes

**Why 13 minutes?** Render Free sleeps after **15 min idle**. 13 < 15, so ping every 13 min keeps alive forever. 750h/month free = 720h used if 24/7, under limit.

**Why /cron endpoint?** cron-job.org free timeout **30s**. Render cold start **30-60s**. `/cron` returns plain text `ok` in **<50ms**, no browser, no JSON, safest for 30s timeout. `/ping` returns JSON in <100ms, also safe. For morning wake-up (50s cold start > 30s timeout), use **Pipedream at 07:50 on /wake** (no timeout limit), then cron-job.org every 13 min 08:00-23:59.

---

## Setup for Both Services (2 Render Accounts)

You have 2 services on 2 separate Render accounts (each 750h free):

- **Account 1 - Lite MCP (120MB):** `https://perchance-mcp-lite.onrender.com`
- **Account 2 - Solver (250MB, Byparr/Camoufox):** `https://perchance-solver.onrender.com`

Each needs its own cron job.

### cron-job.org (Free, No CC)

1. Create account at https://cron-job.org (free, no CC)

2. **Job 1 - Lite MCP:**
   - Dashboard → Create cronjob
   - Title: `perchance-lite-keepalive`
   - URL: `https://perchance-mcp-lite.onrender.com/cron`  (or `/ping` for JSON)
   - Schedule: Every 13 minutes
   - Request method: GET
   - Save

3. **Job 2 - Solver:**
   - Title: `perchance-solver-keepalive`
   - URL: `https://perchance-solver.onrender.com/cron`  (or `/ping`)
   - Schedule: Every 13 minutes
   - Request method: GET
   - Save

4. **Total hours:** 2 services × 24h × 31 days = 1488h, but each workspace has 750h, so 720h per workspace < 750h, OK.

5. **Check logs:** Both services track `ping_count`, `last_cron`, `last_source` - visit `/status` to see:
   - `https://perchance-mcp-lite.onrender.com/status`
   - `https://perchance-solver.onrender.com/status`
   - Should show `last_source: cron-job.org` and increasing `ping_count`

### Pipedream Morning Wake-up (Fixes 30s Timeout Issue)

**Problem:** cron-job.org free timeout 30s, but Render cold start 50s → first morning ping fails, second succeeds after 13 min (app still sleeping 13 min).

**Fix:** Use Pipedream (free, no timeout limit) to wake at 07:50 daily:

1. Create account at https://pipedream.com (free)
2. New Workflow → Schedule → Cron → `0 50 7 * * *` (07:50 UTC daily)
3. Add step: HTTP GET `https://perchance-mcp-lite.onrender.com/wake` and `https://perchance-solver.onrender.com/wake`
4. Deploy

Pipedream has **no 30s timeout**, handles 50s cold start, wakes app at 07:50, then cron-job.org every 13 min 08:00-23:59 keeps alive.

**Alternative:** Use **UptimeRobot** (free, 5 min interval, no 30s timeout issue, better than cron-job.org):
- https://uptimerobot.com → New Monitor → HTTP(s) → URL `https://perchance-mcp-lite.onrender.com/ping` → Every 5 min
- Same for solver
- UptimeRobot doesn't have 30s timeout limit like cron-job.org, more reliable for cold start

---

## Endpoints for cron-job.org

| Endpoint | Response | Time | Use For |
|----------|----------|------|---------|
| `/cron` | `ok` plain text | **<50ms** | **Best for cron-job.org** - ultra-light, no JSON |
| `/keepalive` | `ok` plain text | <50ms | Alias for /cron |
| `/ping` | `{"status":"ok",...}` JSON | <100ms | JSON health, also good for cron-job.org |
| `/healthz`, `/health`, `/api/health` | JSON | <100ms | Aliases |
| `/wake` | `{"status":"ok","message":"woke"}` | <50ms | **For Pipedream morning wake-up** (no timeout) |
| `/status` | Detailed status + solver health + cron info | <200ms | Monitoring |
| `/` | Info + cron setup | <100ms | Info |

All endpoints have `Cache-Control: no-cache` and `X-Robots-Tag: noindex`.

All endpoints are **lightweight, no browser, no Camoufox import** - safe for 512MB and fast.

---

## Code Changes for cron-job.org

**Both services now have:**

1. **Ultra-lightweight `/cron` endpoint:**
```python
@app.get("/cron")
async def cron_endpoint():
    PING_COUNT["count"] += 1
    return PlainTextResponse("ok", headers={"Cache-Control": "no-cache"})
```
- Returns plain text `ok` in <50ms
- No browser, no heavy import, no JSON parsing overhead
- Best for cron-job.org 30s timeout

2. **`/ping` with no-cache headers and source detection:**
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

3. **`/wake` for Pipedream:**
- Returns ok immediately (<50ms) but Render starts warming up in background
- Use Pipedream at 07:50 daily (no timeout) to handle 50s cold start

4. **`/status` with cron monitoring:**
- Shows `uptime`, `ping_count`, `last_cron`, `last_source`, `last_user_agent`
- For lite, also checks solver health via `SOLVER_URL/ping`

5. **HEAD support:**
- All health endpoints support both GET and HEAD (`@app.get` + `@app.head`) for UptimeRobot and Render health checks

---

## Test cron-job.org Setup

```bash
# Test lite
curl https://perchance-mcp-lite.onrender.com/cron
# → ok (plain text, <50ms)

curl https://perchance-mcp-lite.onrender.com/ping
# → {"status":"ok","source":"unknown","ping_count":1,...}

curl https://perchance-mcp-lite.onrender.com/status
# → {"service":"perchance-mcp-lite","uptime_human":"2h 13m","ping_count":10,"last_source":"cron-job.org",...}

# Test solver
curl https://perchance-solver.onrender.com/cron
# → ok

curl https://perchance-solver.onrender.com/status
# → {"service":"perchance-solver","ping_count":10,"last_source":"cron-job.org",...}
```

After setting up cron-job.org jobs, wait 15 min and check `/status` - `ping_count` should increase every 13 min and `last_source` should be `cron-job.org`.

---

## Summary for Both Services Every 13 Minutes

- **Interval:** 13 minutes (13 < 15 min Render sleep)
- **Endpoints:** `/cron` (best, 50ms plain text) or `/ping` (JSON, 100ms)
- **Timeout:** cron-job.org free 30s, our endpoints <100ms safe, but cold start 50s may timeout first morning ping → use Pipedream at 07:50 on `/wake` (no timeout) + cron-job.org 08:00-23:59
- **Hours:** 720h/month per service < 750h free limit
- **Both services:** Need 2 cron jobs (one per Render account) - lite and solver
- **Better alternative:** UptimeRobot every 5 min on `/ping` - no 30s timeout issue, more reliable

Setup now and both services stay alive 24/7 on Render free tier.
