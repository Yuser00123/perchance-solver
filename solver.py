"""
Perchance Turnstile Solver Service - Byparr/Camoufox based, cron-job.org optimized
Host on separate Render account (512MB-1GB) to keep main MCP under 120MB

Endpoints:
  GET / - info
  GET /ping, /healthz, /health, /cron, /keepalive, /wake, /status - lightweight health (no browser) for cron-job.org every 13 min
  POST /solve - Solve Turnstile for Perchance, return userKey + browserId
  POST /generate - Solve + generate image via curl_cffi, return image
  POST /v1 - FlareSolverr-compatible API (drop-in for Byparr clients)

For Perchance sitekey: 0x4AAAAAAAA8g8NphwaSOT59
Page: https://image-generation.perchance.org/embed

This service uses Camoufox (Firefox-based stealth, same as Byparr) - 200MB vs 400MB+ for Chromium,
C++ level fingerprint patching, passes CreepJS, best for Turnstile.

Memory: ~250-350MB (fits Render 512MB), vs 800MB for SeleniumBase UC
Unlimited: Yes, self-hosted, no Browserless 1000/mo limit

cron-job.org: 13 min interval < 15 min Render sleep threshold, 750h/month = 720h used < 750h limit
cron-job.org free timeout 30s, so /ping and /cron must respond <100ms (no browser)
For morning wake-up (50s cold start > 30s timeout), use Pipedream at 07:50 on /wake (no timeout)
"""

import os
import re
import json
import time
import random
import secrets
import base64
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# Setup LD_LIBRARY_PATH for Camoufox Firefox deps
def _setup_ld():
    possible = [
        "/tmp/debs/out/usr/lib/x86_64-linux-gnu",
        "/home/user/.perchance-deps/lib",
        "/usr/lib/x86_64-linux-gnu",
        "/app/.perchance-deps/lib",
    ]
    cur = os.environ.get("LD_LIBRARY_PATH", "")
    for p in possible:
        if os.path.exists(p) and p not in cur:
            os.environ["LD_LIBRARY_PATH"] = f"{p}:{cur}" if cur else p
            cur = os.environ["LD_LIBRARY_PATH"]

_setup_ld()

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
import httpx

# Perchance constants
BASE_EMBED = "https://image-generation.perchance.org"
BASE_PERCHANCE = "https://perchance.org"
API_VERIFY = f"{BASE_EMBED}/api/verifyUser"
API_GENERATE = f"{BASE_EMBED}/api/generate"
API_AD_CODE = f"{BASE_PERCHANCE}/api/getAccessCodeForAdPoweredStuff"
CLIENT_VERSION_HASH = "9b43eec2e71907610e4e9317b54c208495f6850086e92239a869811d2e2d77ee"

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

CACHE_DIR = Path.home() / ".perchance-solver"
CACHE_DIR.mkdir(exist_ok=True)
BROWSER_ID_FILE = CACHE_DIR / "browser_id.txt"
USER_KEY_FILE = CACHE_DIR / "user_key.txt"

# Track startup and pings for cron-job.org monitoring
START_TIME = time.time()
PING_COUNT = {"count": 0, "last_cron": None, "last_ua": None, "last_source": None}

def generate_browser_id() -> str:
    return secrets.token_hex(16)

def load_cached_browser_id() -> str:
    if BROWSER_ID_FILE.exists():
        bid = BROWSER_ID_FILE.read_text().strip()
        if re.fullmatch(r"[a-f0-9]{32}", bid):
            return bid
    bid = generate_browser_id()
    BROWSER_ID_FILE.write_text(bid)
    return bid

def save_user_key(key: str):
    USER_KEY_FILE.write_text(key)

def load_cached_user_key() -> Optional[str]:
    if USER_KEY_FILE.exists():
        k = USER_KEY_FILE.read_text().strip()
        m = re.search(r"[a-f0-9]{64}", k)
        if m:
            return m.group(0)
    return None

# --- Camoufox Turnstile Solver (Byparr-style) ---

async def get_user_key_via_camoufox(timeout: int = 60) -> Optional[Dict[str, Any]]:
    """
    Solve Turnstile via Camoufox (Firefox stealth, same as Byparr)
    Returns {userKey, browserId, token} or None
    Falls back to SeleniumBase UC if Camoufox not available (for sandbox testing)
    """
    # Try Camoufox first (Byparr browser, 200MB, best for Turnstile)
    try:
        from camoufox.async_api import AsyncCamoufox
        print("[Solver] Trying Camoufox (Byparr browser)...")
        browser_id = load_cached_browser_id()
        
        try:
            async with AsyncCamoufox(headless=True, humanize=True, os="windows") as browser:
                page = await browser.new_page()
                import urllib.parse
                hash_data = {
                    "prompt": "test",
                    "seed": 0,
                    "resolution": "512x512",
                    "guidanceScale": 7,
                    "negativePrompt": "",
                    "requestId": f"camou_{random.random()}",
                    "iframeId": "test"
                }
                url = f"{BASE_EMBED}/embed#{urllib.parse.quote(json.dumps(hash_data))}"
                page.on("console", lambda msg: print(f"[Camoufox CONSOLE {msg.type}] {msg.text[:500]}"))

                await page.goto(url)
                await page.wait_for_timeout(5000)

                result = await page.evaluate("""async () => {
                    const bid = localStorage.getItem('generation-v2-browser');
                    if(!window.turnstile){
                        await new Promise((res) => {
                            window.onloadTurnstileCallback = () => res();
                            const s = document.createElement('script');
                            s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?onload=onloadTurnstileCallback';
                            s.onerror = () => res();
                            document.body.appendChild(s);
                            setTimeout(() => res(), 10000);
                        });
                        await new Promise(r => setTimeout(r, 2000));
                    }
                    if(!window.turnstile){
                        return {error: 'turnstile still undefined', bid};
                    }
                    let ctn = document.querySelector('#cfTurnstileCtn');
                    if(!ctn){
                        ctn = document.createElement('div');
                        ctn.id = 'cfTurnstileCtn';
                        document.body.appendChild(ctn);
                    }
                    try{
                        const token = await new Promise((resolve) => {
                            let settled = false;
                            const timer = setTimeout(() => {if(!settled){settled=true;resolve(null);}},40000);
                            window.cloudflareTurnstileTokenResolver = (t) => {if(!settled){settled=true;clearTimeout(timer);resolve(t);}};
                            try{
                                window.turnstile.render('#cfTurnstileCtn', {
                                    sitekey: '0x4AAAAAAAA8g8NphwaSOT59',
                                    callback: (t) => window.cloudflareTurnstileTokenResolver(t),
                                    'error-callback': () => {if(!settled){settled=true;clearTimeout(timer);resolve(null);}}
                                });
                            }catch(e){ if(!settled){settled=true;clearTimeout(timer);resolve(null);} }
                        });
                        if(!token){ return {error: 'no token after 40s', bid}; }
                        const verifyUrl = `/api/verifyUser?browserId=${bid}&token=${encodeURIComponent(token)}&thread=0&__cacheBust=${Math.random()}`;
                        const r = await fetch(verifyUrl);
                        const txt = await r.text();
                        let j; try{ j = JSON.parse(txt); }catch(e){ return {error: 'verify not json '+txt.slice(0,500), bid}; }
                        return {bid, response: j, token};
                    }catch(e){ return {error: 'exception '+e.toString(), bid}; }
                }""")

                print(f"[Solver] Camoufox verify result: {result}")
                user_key = result.get('response', {}).get('userKey') if isinstance(result, dict) else None
                if user_key and re.fullmatch(r"[a-f0-9]{64}", user_key):
                    print(f"[Solver] Got userKey via Camoufox: {user_key[:12]}...")
                    save_user_key(user_key)
                    return {"userKey": user_key, "browserId": result.get('bid', browser_id), "token": result.get('token', '')[:100], "method": "camoufox"}
        except Exception as e:
            print(f"[Solver] Camoufox inner failed: {e}, falling back to SeleniumBase UC")
    except Exception as e:
        print(f"[Solver] Camoufox outer failed: {e}, falling back to SeleniumBase UC")
    
    # Fallback to SeleniumBase UC Mode (tested working in sandbox, 800MB but reliable)
    print("[Solver] Trying SeleniumBase UC Mode (fallback, tested working in sandbox)...")
    try:
        from seleniumbase import SB
        import glob
        chromium_candidates = glob.glob("/home/user/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")
        chromium_path = chromium_candidates[0] if chromium_candidates else None
        print(f"[Solver] Chromium path: {chromium_path}")

        def _run_sync():
            with SB(uc=True, headless=True, chromium_arg="--no-sandbox --disable-gpu --disable-dev-shm-usage --disable-blink-features=AutomationControlled", binary_location=chromium_path) as sb:
                import json as _json, urllib.parse as _up, random as _rand
                hash_data = {"prompt": "test", "seed": 0, "resolution": "512x512", "guidanceScale": 7, "negativePrompt": "", "requestId": f"sb_{_rand.random()}", "iframeId": "test"}
                url = f"{BASE_EMBED}/embed#{_up.quote(_json.dumps(hash_data))}"
                sb.open(url)
                sb.sleep(6)
                result = sb.execute_async_script("""
                    const callback = arguments[arguments.length - 1];
                    (async () => {
                        const bid = localStorage.getItem('generation-v2-browser');
                        if(!window.turnstile){
                            window.onloadTurnstileCallback = () => {};
                            const s = document.createElement('script');
                            s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?onload=onloadTurnstileCallback';
                            document.body.appendChild(s);
                            await new Promise(r => setTimeout(r, 5000));
                        }
                        if(!window.turnstile){
                            callback({error: 'no turnstile', bid});
                            return;
                        }
                        let ctn = document.querySelector('#cfTurnstileCtn');
                        if(!ctn){
                            ctn = document.createElement('div');
                            ctn.id = 'cfTurnstileCtn';
                            document.body.appendChild(ctn);
                        }
                        try{
                            const token = await new Promise((resolve) => {
                                let settled=false;
                                const timer=setTimeout(()=>{if(!settled){settled=true;resolve(null);}},35000);
                                window.cloudflareTurnstileTokenResolver=(t)=>{if(!settled){settled=true;clearTimeout(timer);resolve(t);}};
                                window.turnstile.render('#cfTurnstileCtn', {
                                    sitekey: '0x4AAAAAAAA8g8NphwaSOT59',
                                    callback: (t)=>window.cloudflareTurnstileTokenResolver(t),
                                    'error-callback': ()=>{if(!settled){settled=true;clearTimeout(timer);resolve(null);}}
                                });
                            });
                            if(!token){
                                callback({error: 'no token', bid});
                                return;
                            }
                            const verifyUrl = `/api/verifyUser?browserId=${bid}&token=${encodeURIComponent(token)}&thread=0&__cacheBust=${Math.random()}`;
                            const r = await fetch(verifyUrl);
                            const txt = await r.text();
                            let j;
                            try{ j=JSON.parse(txt); }catch(e){ callback({error: 'verify not json '+txt.slice(0,500), bid}); return; }
                            callback({bid, response: j, token});
                        }catch(e){
                            callback({error: 'exception '+e.toString(), bid});
                        }
                    })();
                """, timeout=60)
                return result

        result = await asyncio.to_thread(_run_sync)
        print(f"[Solver] SeleniumBase result: {result}")
        user_key = result.get('response', {}).get('userKey') if isinstance(result, dict) else None
        if user_key and re.fullmatch(r"[a-f0-9]{64}", user_key):
            print(f"[Solver] Got userKey via SeleniumBase: {user_key[:12]}...")
            save_user_key(user_key)
            return {"userKey": user_key, "browserId": result.get('bid', load_cached_browser_id()), "token": result.get('token','')[:100], "method": "seleniumbase-uc"}
        return None
    except Exception as e:
        print(f"[Solver] SeleniumBase also failed: {e}")
        import traceback; traceback.print_exc()
        return None

# --- curl_cffi for ad code + generate (no browser, lightweight) ---

def get_ad_code_via_curl_cffi_sync() -> str:
    try:
        from curl_cffi import requests as curl_requests
        cache_bust = int(time.time() // (60 * 10))
        url = f"{API_AD_CODE}?__cacheBust={cache_bust}"
        headers = {
            "Referer": f"{BASE_PERCHANCE}/stable-diffusion-ai",
            "Origin": BASE_PERCHANCE,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = curl_requests.get(url, impersonate="chrome", headers=headers, timeout=15)
        if resp.status_code == 200:
            code = resp.text.strip()
            if re.fullmatch(r"[a-f0-9]{64}", code):
                print(f"[Solver] Got ad code via curl_cffi: {code[:12]}...")
                return code
    except Exception as e:
        print(f"[Solver] curl_cffi ad code failed: {e}")
    return ""

async def get_ad_code_via_curl_cffi() -> str:
    return await asyncio.to_thread(get_ad_code_via_curl_cffi_sync)

async def generate_via_curl_cffi(prompt: str, negative_prompt: str = "", seed: int = -1, resolution: str = "512x512", guidance_scale: float = 7.0, user_key: str = "", ad_code: str = "", browser_id: str = "") -> Dict[str, Any]:
    try:
        from curl_cffi import requests as curl_requests
        import urllib.parse

        request_id = f"0.{secrets.randbits(30)}"
        cache_bust = random.random()
        params = {
            "userKey": user_key,
            "requestId": request_id,
            "adAccessCode": ad_code,
            "v": CLIENT_VERSION_HASH,
            "__cacheBust": cache_bust
        }
        body = {
            "prompt": prompt,
            "negativePrompt": negative_prompt,
            "seed": seed,
            "resolution": resolution,
            "guidanceScale": guidance_scale,
            "channel": "stable-diffusion-ai",
            "subChannel": "public",
            "userKey": user_key,
            "adAccessCode": ad_code,
            "requestId": request_id
        }
        headers = {
            "Referer": f"{BASE_EMBED}/embed",
            "Origin": BASE_EMBED,
            "Content-Type": "application/json",
            "Accept": "*/*",
        }
        url = f"{API_GENERATE}?{urllib.parse.urlencode(params)}"

        def _do_generate():
            sess = curl_requests.Session(impersonate="chrome")
            r = sess.post(url, json=body, headers=headers, timeout=30)
            return {"status": r.status_code, "text": r.text[:10000], "json": r.json() if r.text.strip().startswith("{") else None}

        gen_result = await asyncio.to_thread(_do_generate)
        print(f"[Solver] Generate result status {gen_result['status']} {gen_result['text'][:2000]}")

        try:
            data = json.loads(gen_result['text'])
        except Exception:
            data = gen_result.get('json')

        if not data or data.get('status') != 'success':
            raise RuntimeError(f"Generation failed: {gen_result['text'][:1000]}")

        image_id = data.get('imageId')
        proxy_download = data.get('imageDownloadUrl')
        file_ext = data.get('fileExtension', 'jpeg')
        seed_used = data.get('seed', seed)

        if data.get('imageDataUrls') and len(data['imageDataUrls']) > 0:
            data_url = data['imageDataUrls'][0]
            b64_part = data_url.split(',', 1)[1] if ',' in data_url else ''
            image_bytes = base64.b64decode(b64_part)
            return {
                "status": "success",
                "imageId": image_id,
                "imageDownloadUrl": proxy_download,
                "fileExtension": file_ext,
                "seed": seed_used,
                "dataUrl": data_url,
                "imageBytes": image_bytes,
                "width": data.get('width'),
                "height": data.get('height'),
            }

        def _do_download():
            sess = curl_requests.Session(impersonate="chrome")
            urls = []
            if proxy_download:
                urls.append(proxy_download if proxy_download.startswith('http') else f"{BASE_EMBED}{proxy_download}")
            if image_id:
                urls.append(f"{BASE_EMBED}/api/downloadTemporaryImage?imageId={image_id}")
            for dl_url in urls:
                try:
                    r = sess.get(dl_url, headers={"Referer": f"{BASE_EMBED}/embed", "Origin": BASE_EMBED}, timeout=30)
                    if r.status_code == 200 and len(r.content) > 1000:
                        print(f"[Solver] Downloaded {len(r.content)} bytes from {dl_url[:100]}")
                        return {"ok": True, "bytes": r.content, "url": dl_url}
                except Exception as e:
                    print(f"[Solver] Download error {dl_url}: {e}")
            return {"ok": False}

        dl_result = await asyncio.to_thread(_do_download)
        if not dl_result.get('ok'):
            raise RuntimeError(f"Download failed. Keys: {list(data.keys())}")

        image_bytes = dl_result['bytes']
        data_url = f"data:image/{file_ext};base64,{base64.b64encode(image_bytes).decode()}"

        return {
            "status": "success",
            "imageId": image_id,
            "imageDownloadUrl": proxy_download,
            "fileExtension": file_ext,
            "seed": seed_used,
            "dataUrl": data_url,
            "imageBytes": image_bytes,
            "width": data.get('width'),
            "height": data.get('height'),
        }

    except Exception as e:
        print(f"[Solver] generate_via_curl_cffi failed: {e}")
        raise

# --- FastAPI App with cron-job.org optimization ---

app = FastAPI(
    title="Perchance Turnstile Solver - Byparr/Camoufox + cron-job.org 13min",
    description="Self-hosted Turnstile solver for Perchance (sitekey 0x4AAAAAAAA8g8NphwaSOT59) using Camoufox Firefox stealth (same as Byparr). Optimized for cron-job.org every 13 min keep-alive (13 < 15 min Render sleep).",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

class SolveRequest(BaseModel):
    browserId: Optional[str] = None

class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""
    seed: int = -1
    resolution: str = "512x512"
    guidance_scale: float = 7.0
    channel: str = "stable-diffusion-ai"

class FlareSolverrRequest(BaseModel):
    cmd: str
    url: str
    maxTimeout: int = 60000
    session: Optional[str] = None
    cookies: Optional[list] = None
    postData: Optional[str] = None

def _get_cron_source(request: Request) -> str:
    ua = request.headers.get("user-agent", "").lower()
    if "cron-job.org" in ua:
        return "cron-job.org"
    elif "uptimerobot" in ua:
        return "uptimerobot"
    elif "render" in ua or "health" in ua:
        return "render-health"
    elif "pipedream" in ua:
        return "pipedream"
    return "unknown"

@app.get("/")
async def root():
    uptime = int(time.time() - START_TIME)
    return {
        "name": "perchance-turnstile-solver",
        "status": "ok",
        "version": "1.0.0",
        "description": "Byparr/Camoufox based solver for Perchance Turnstile sitekey 0x4AAAAAAAA8g8NphwaSOT59 - cron-job.org 13min optimized",
        "uptime_seconds": uptime,
        "uptime_human": f"{uptime//3600}h {(uptime%3600)//60}m {uptime%60}s",
        "ping_count": PING_COUNT["count"],
        "endpoints": {
            "/ping": "Health check for cron-job.org every 13 min (lightweight, <100ms, no browser) - USE THIS",
            "/cron": "Ultra-lightweight cron endpoint (plain text 'ok' in <50ms) - BEST FOR cron-job.org",
            "/keepalive": "Alias for /cron",
            "/wake": "Wake endpoint for Pipedream morning wake-up (handles 50s cold start > 30s cron timeout)",
            "/status": "Detailed status with uptime, ping count, cron source",
            "/solve": "POST Solve Turnstile, return userKey + browserId",
            "/generate": "POST Generate image (solve + curl_cffi)",
            "/v1": "POST FlareSolverr-compatible API (Byparr drop-in)",
            "/docs": "Swagger UI"
        },
        "cron_job_org": {
            "interval": "13 minutes (13 < 15 min Render sleep threshold)",
            "timeout": "30s free limit, our /ping and /cron respond <100ms, safe",
            "hours_per_month": "720h if kept alive 24/7, under 750h Render free limit per workspace",
            "setup_both_services": [
                "Job 1: https://perchance-mcp-lite.onrender.com/cron every 13 min (Render Acc 1)",
                "Job 2: https://perchance-solver.onrender.com/cron every 13 min (Render Acc 2)"
            ],
            "morning_wake": "Pipedream at 07:50 daily on /wake (no 30s timeout) handles 50s cold start, then cron-job.org every 13 min 08:00-23:59",
            "alternative": "UptimeRobot every 5 min on /ping (no timeout issue, better than cron-job.org)"
        },
        "stack": "Camoufox Firefox stealth (Byparr) + curl_cffi",
        "memory": "~250-350MB (fits Render 512MB)",
        "unlimited": True,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# Ultra-lightweight endpoints for cron-job.org - must respond <100ms, no browser
@app.get("/ping")
@app.head("/ping")
@app.get("/healthz")
@app.head("/healthz")
@app.get("/health")
@app.head("/health")
@app.get("/api/health")
async def health(request: Request):
    """Lightweight health for cron-job.org every 13 min - <100ms, no browser, no Camoufox import"""
    PING_COUNT["count"] += 1
    PING_COUNT["last_cron"] = datetime.now(timezone.utc).isoformat()
    PING_COUNT["last_ua"] = request.headers.get("user-agent", "")[:200]
    PING_COUNT["last_source"] = _get_cron_source(request)
    
    return JSONResponse(
        content={
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime": int(time.time() - START_TIME),
            "ping_count": PING_COUNT["count"],
            "service": "perchance-solver",
            "memory": "250-350MB (Camoufox)",
            "source": PING_COUNT["last_source"],
            "cron_interval": "13 min (keep alive, 13 < 15 min sleep)",
            "note": "Use /cron for ultra-lightweight plain text (50ms) - best for cron-job.org 30s timeout"
        },
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Robots-Tag": "noindex"
        }
    )

@app.get("/cron")
@app.head("/cron")
@app.get("/keepalive")
@app.head("/keepalive")
async def cron_endpoint(request: Request):
    """Ultra-lightweight for cron-job.org - plain text 'ok' in <50ms, no JSON overhead, safest for 30s timeout"""
    PING_COUNT["count"] += 1
    PING_COUNT["last_cron"] = datetime.now(timezone.utc).isoformat()
    PING_COUNT["last_ua"] = request.headers.get("user-agent", "")[:200]
    PING_COUNT["last_source"] = _get_cron_source(request)
    
    return PlainTextResponse(
        content="ok",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Robots-Tag": "noindex",
            "Content-Type": "text/plain"
        }
    )

@app.get("/wake")
@app.head("/wake")
async def wake_endpoint(request: Request):
    """
    Wake endpoint for Pipedream morning wake-up
    Returns ok immediately (<50ms) but Render will start warming up
    Use Pipedream (no 30s timeout) at 07:50 daily to handle 50s cold start > cron-job.org 30s timeout
    Then cron-job.org every 13 min 08:00-23:59 keeps alive
    """
    PING_COUNT["count"] += 1
    PING_COUNT["last_cron"] = datetime.now(timezone.utc).isoformat()
    PING_COUNT["last_source"] = _get_cron_source(request)
    
    return JSONResponse(
        content={
            "status": "ok",
            "message": "woke",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime": int(time.time() - START_TIME),
            "ping_count": PING_COUNT["count"],
            "note": "Pipedream morning wake-up (no timeout) handles 50s cold start, then cron-job.org every 13 min"
        },
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@app.get("/status")
async def status_endpoint(request: Request):
    """Detailed status for monitoring both services"""
    uptime = int(time.time() - START_TIME)
    return {
        "service": "perchance-solver",
        "status": "ok",
        "memory": "250-350MB (Camoufox)",
        "uptime_seconds": uptime,
        "uptime_human": f"{uptime//3600}h {(uptime%3600)//60}m {uptime%60}s",
        "ping_count": PING_COUNT["count"],
        "last_cron": PING_COUNT["last_cron"],
        "last_source": PING_COUNT["last_source"],
        "last_user_agent": PING_COUNT["last_ua"],
        "cron_job_org": {
            "interval": "13 minutes",
            "reason": "13 < 15 min Render sleep threshold",
            "hours_used": f"{uptime//3600}h (max 750h/month free per workspace)",
            "urls_to_ping": [
                "https://perchance-mcp-lite.onrender.com/cron (Render Acc 1, lite 120MB)",
                "https://perchance-solver.onrender.com/cron (Render Acc 2, solver 250MB, this service)"
            ],
            "setup": "cron-job.org → Create job → URL https://.../cron → every 13 min → save. Or UptimeRobot every 5 min on /ping (better, no 30s timeout)",
            "morning_wake": "Pipedream at 07:50 on /wake (no timeout) for 50s cold start, then cron-job.org 08:00-23:59"
        },
        "solver": {
            "sitekey": "0x4AAAAAAAA8g8NphwaSOT59",
            "page": "https://image-generation.perchance.org/embed",
            "method": "Camoufox Firefox stealth (Byparr)",
            "endpoints": ["/solve", "/generate", "/v1"]
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.post("/solve")
async def solve_turnstile(req: SolveRequest = SolveRequest()):
    """Solve Turnstile for Perchance and return fresh userKey (64 hex, valid ~30s, IP-bound)"""
    try:
        result = await get_user_key_via_camoufox()
        if not result:
            raise HTTPException(status_code=500, detail="Failed to solve Turnstile via Camoufox")
        
        return {
            "status": "success",
            "userKey": result["userKey"],
            "browserId": result["browserId"],
            "method": result["method"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "expires_in": 30,
            "note": "userKey is IP-bound to solver's IP, must generate via solver or same IP"
        }
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"Solve failed: {str(e)} {tb[:1000]}")

@app.post("/generate")
async def generate_image(req: GenerateRequest):
    """Full generation: solve Turnstile if needed + generate via curl_cffi + download"""
    try:
        ad_code = await get_ad_code_via_curl_cffi()
        solve_result = await get_user_key_via_camoufox()
        if not solve_result:
            raise HTTPException(status_code=500, detail="Failed to get userKey via Camoufox")
        
        user_key = solve_result["userKey"]
        browser_id = solve_result["browserId"]

        gen_result = await generate_via_curl_cffi(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt,
            seed=req.seed,
            resolution=req.resolution,
            guidance_scale=req.guidance_scale,
            user_key=user_key,
            ad_code=ad_code,
            browser_id=browser_id
        )

        image_bytes = gen_result["imageBytes"]
        b64 = base64.b64encode(image_bytes).decode()

        return {
            "status": "success",
            "prompt": req.prompt,
            "seed": gen_result.get("seed", req.seed),
            "resolution": req.resolution,
            "imageId": gen_result.get("imageId"),
            "fileExtension": gen_result.get("fileExtension", "jpeg"),
            "fileSize": len(image_bytes),
            "dataUrl": f"data:image/{gen_result.get('fileExtension','jpeg')};base64,{b64[:100]}... (truncated)",
            "dataUrlFull": f"data:image/{gen_result.get('fileExtension','jpeg')};base64,{b64}",
            "imageBase64": b64,
            "userKey": f"{user_key[:12]}...{user_key[-6:]}",
            "browserId": browser_id,
            "method": "byparr/camoufox + curl_cffi",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"Generate failed: {str(e)} {tb[:2000]}")

@app.post("/v1")
async def flaresolverr_compatible(req: FlareSolverrRequest):
    """FlareSolverr-compatible API for drop-in replacement"""
    try:
        if req.cmd not in ["request.get", "request.post"]:
            raise HTTPException(status_code=400, detail=f"Unsupported cmd {req.cmd}, use request.get")

        from camoufox.async_api import AsyncCamoufox

        print(f"[FlareSolverr API] cmd={req.cmd} url={req.url} timeout={req.maxTimeout}")

        async with AsyncCamoufox(headless=True, humanize=True, os="windows") as browser:
            page = await browser.new_page()
            await page.goto(req.url, timeout=req.maxTimeout)
            await page.wait_for_timeout(5000)

            cookies = await page.context.cookies()
            flare_cookies = [{"name": c["name"], "value": c["value"], "domain": c["domain"]} for c in cookies]
            ua = await page.evaluate("() => navigator.userAgent")
            html = await page.content()

            return {
                "status": "ok",
                "message": "Challenge solved (Camoufox/Byparr)",
                "solution": {
                    "url": req.url,
                    "status": 200,
                    "cookies": flare_cookies,
                    "userAgent": ua,
                    "response": html[:10000],
                    "headers": {}
                },
                "startTimestamp": int(time.time()*1000),
                "endTimestamp": int(time.time()*1000),
                "version": "1.0.0-byparr-camoufox"
            }

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[FlareSolverr API] Error: {e} {tb[:1000]}")
        raise HTTPException(status_code=500, detail=f"FlareSolverr compat failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", os.getenv("WEBSITES_PORT", "8000")))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting Perchance Solver (Byparr/Camoufox) cron-job.org 13min ready on {host}:{port}")
    uvicorn.run("solver:app", host=host, port=port, log_level="info")
