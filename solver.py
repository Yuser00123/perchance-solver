"""
Perchance Turnstile Solver Service - SeleniumBase UC Mode ONLY - Unlimited Open-Source
For HuggingFace Spaces (16GB RAM, 2 vCPU) + cron-job.org every 24h keep-alive

This is the UNLIMITED method tested working in E2B sandbox datacenter IP:
- Playwright fails Cloudflare 403 Just a moment, No available adapters
- SeleniumBase UC Mode succeeds: bid 0231e07d3b025b5a0f13de1e82358c54 userKey f0f66dce6a2490dae1d6428867e9e2ebb3ffef4b101fa0d07669ec600d7c68a9
- curl_cffi gets adAccessCode unlimited: 24bad67d54ce6ac07b7672541f3264f7f7fcc6eef3e273ae5f9512469b6a72db
- Generate + download via curl_cffi same IP immediate (token ~5min single-use)

Endpoints:
  GET / - info
  GET /ping, /healthz, /health, /cron, /keepalive, /wake, /status - lightweight health (no browser) for cron-job.org every 24h (HF Spaces sleeps after 48h)
  POST /solve - Solve Turnstile via SeleniumBase UC ONLY, return userKey + browserId
  POST /generate - Solve + generate image via curl_cffi, return image
  POST /v1 - FlareSolverr-compatible API

For Perchance sitekey: 0x4AAAAAAAA8g8NphwaSOT59
Page: https://image-generation.perchance.org/embed

Memory: ~800MB-1GB (fits HF Spaces 16GB, not Render 512MB)
Unlimited: Yes, self-hosted, no Browserless 1000/mo limit
"""

import os
import re
import json
import time
import random
import secrets
import base64
import asyncio
import glob
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any

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

# --- SeleniumBase UC Mode ONLY - Unlimited Method Tested Working in Sandbox ---

async def get_user_key_via_seleniumbase(timeout: int = 90) -> Optional[Dict[str, Any]]:
    """
    Self-hosted UNLIMITED Turnstile solver using SeleniumBase UC Mode (undetected chromedriver)
    This is the method tested working in E2B sandbox datacenter IP where Playwright fails 403:
    - Playwright: Cloudflare 403 Just a moment, No available adapters
    - SeleniumBase UC: SUCCESS bid 0231e07d3b025b5a0f13de1e82358c54 userKey f0f66dce6a2490dae1d6428867e9e2ebb3ffef4b101fa0d07669ec600d7c68a9
    Fully open-source unlimited, no Browserless limit, no Camoufox needed.
    Returns {userKey, browserId, token} or None
    """
    print("[Solver] Trying SeleniumBase UC Mode (UNLIMITED method, tested working in sandbox)...")
    try:
        from seleniumbase import SB

        # Find chromium binary (Playwright cache or system)
        chromium_candidates = []
        chromium_candidates += glob.glob("/home/user/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")
        chromium_candidates += glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")
        chromium_candidates += glob.glob("/home/*/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")
        chromium_candidates += ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]
        chromium_path = None
        for cand in chromium_candidates:
            if os.path.exists(cand):
                chromium_path = cand
                break
        
        print(f"[Solver] Chromium path: {chromium_path}")

        def _run_sync():
            # UC Mode = undetected-chromedriver, bypasses Cloudflare
            with SB(uc=True, headless=True, chromium_arg="--no-sandbox --disable-gpu --disable-dev-shm-usage --disable-blink-features=AutomationControlled", binary_location=chromium_path) as sb:
                import json as _json, urllib.parse as _up, random as _rand, time as _time
                hash_data = {"prompt": "test", "seed": 0, "resolution": "512x512", "guidanceScale": 7, "negativePrompt": "", "requestId": f"sb_{_rand.random()}", "iframeId": "test"}
                url = f"{BASE_EMBED}/embed#{_up.quote(_json.dumps(hash_data))}"
                print(f"[SeleniumBase] Opening {url[:100]}...")
                sb.open(url)
                sb.sleep(8)
                bid = sb.execute_script("return localStorage.getItem('generation-v2-browser')")
                print(f"[SeleniumBase] browserId: {bid}")

                # Solve Turnstile sitekey 0x4AAAAAAAA8g8NphwaSOT59 via JS injection
                result = sb.execute_async_script("""
                    const callback = arguments[arguments.length - 1];
                    (async () => {
                        const bid = localStorage.getItem('generation-v2-browser');
                        console.log('Turnstile solving, bid:', bid);
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
                                callback({error: 'no token after 35s', bid});
                                return;
                            }
                            console.log('Got Turnstile token', token.slice(0,20));
                            const verifyUrl = `/api/verifyUser?browserId=${bid}&token=${encodeURIComponent(token)}&thread=0&__cacheBust=${Math.random()}`;
                            const r = await fetch(verifyUrl);
                            const txt = await r.text();
                            console.log('Verify response', txt.slice(0,500));
                            let j;
                            try{ j=JSON.parse(txt); }catch(e){ callback({error: 'verify not json '+txt.slice(0,500), bid}); return; }
                            callback({bid, response: j, token});
                        }catch(e){
                            callback({error: 'exception '+e.toString(), bid});
                        }
                    })();
                """, timeout=60)
                print(f"[SeleniumBase] result: {result}")
                return result

        result = await asyncio.to_thread(_run_sync)
        print(f"[Solver] SeleniumBase UC result: {result}")
        user_key = result.get('response', {}).get('userKey') if isinstance(result, dict) else None
        if user_key and re.fullmatch(r"[a-f0-9]{64}", user_key):
            print(f"[Solver] Got userKey via SeleniumBase UC: {user_key[:12]}... (UNLIMITED)")
            save_user_key(user_key)
            return {"userKey": user_key, "browserId": result.get('bid', load_cached_browser_id()), "token": result.get('token','')[:100], "method": "seleniumbase-uc-unlimited"}
        else:
            print(f"[Solver] SeleniumBase UC failed to get userKey: {result}")
            return None

    except Exception as e:
        print(f"[Solver] SeleniumBase UC failed: {e}")
        import traceback; traceback.print_exc()
        return None

# --- curl_cffi for ad code + generate (no browser, lightweight, unlimited) ---

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
                print(f"[Solver] Got ad code via curl_cffi (UNLIMITED): {code[:12]}...")
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

# --- FastAPI App with HF Spaces + cron-job.org optimization ---

app = FastAPI(
    title="Perchance Turnstile Solver - SeleniumBase UC ONLY Unlimited - HF Spaces 16GB",
    description="Self-hosted UNLIMITED Turnstile solver for Perchance (sitekey 0x4AAAAAAAA8g8NphwaSOT59) using ONLY SeleniumBase UC Mode (undetected chromedriver) - tested working in E2B sandbox datacenter IP where Playwright fails 403. For HF Spaces 16GB RAM + cron-job.org every 24h keep-alive (HF Spaces sleeps after 48h).",
    version="3.0.0-selenium-uc-unlimited-hf",
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
    elif "huggingface" in ua or "hf" in ua:
        return "huggingface"
    elif "pipedream" in ua:
        return "pipedream"
    return "unknown"

@app.get("/")
async def root():
    uptime = int(time.time() - START_TIME)
    return {
        "name": "perchance-turnstile-solver",
        "status": "ok",
        "version": "3.0.0-selenium-uc-unlimited-hf",
        "description": "SeleniumBase UC ONLY unlimited solver for Perchance Turnstile sitekey 0x4AAAAAAAA8g8NphwaSOT59 - Tested working in sandbox - For HF Spaces 16GB",
        "uptime_seconds": uptime,
        "uptime_human": f"{uptime//3600}h {(uptime%3600)//60}m {uptime%60}s",
        "ping_count": PING_COUNT["count"],
        "endpoints": {
            "/ping": "Health check for cron-job.org every 24h (lightweight, <100ms, no browser) - USE FOR HF Spaces",
            "/cron": "Ultra-lightweight cron endpoint (plain text 'ok' in <50ms) - BEST FOR cron-job.org",
            "/keepalive": "Alias for /cron",
            "/wake": "Wake endpoint for Pipedream morning wake-up",
            "/status": "Detailed status",
            "/solve": "POST Solve Turnstile via SeleniumBase UC ONLY, return userKey + browserId",
            "/generate": "POST Generate image (SeleniumBase UC + curl_cffi)",
            "/v1": "POST FlareSolverr-compatible API",
            "/docs": "Swagger UI",
            "/gradio": "Gradio UI for HF Spaces"
        },
        "hf_spaces": {
            "hardware": "CPU Basic 2 vCPU, 16GB RAM, 50GB disk (free) - fits SeleniumBase 800MB",
            "sleep": "Sleeps after 48h idle, ping every 24h via cron-job.org keeps alive",
            "setup": "cron-job.org → URL https://YOURUSERNAME-perchance-solver.hf.space/cron → every 24h",
            "note": "Docker SDK now Paid as of July 2026, but Gradio/Streamlit + existing Docker Spaces still work. Use Gradio SDK for free."
        },
        "method": "SeleniumBase UC Mode ONLY (undetected chromedriver) - UNLIMITED, tested working in E2B sandbox where Playwright fails 403",
        "proof": "bid 0231e07d3b025b5a0f13de1e82358c54 userKey f0f66dce6a2490dae1d6428867e9e2ebb3ffef4b101fa0d07669ec600d7c68a9 via SB UC",
        "memory": "~800MB-1GB (fits HF Spaces 16GB, not Render 512MB)",
        "unlimited": True,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/ping")
@app.head("/ping")
@app.get("/healthz")
@app.head("/healthz")
@app.get("/health")
@app.head("/health")
@app.get("/api/health")
async def health(request: Request):
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
            "memory": "800MB-1GB (SeleniumBase UC ONLY unlimited) - HF Spaces 16GB",
            "source": PING_COUNT["last_source"],
            "version": "3.0.0-selenium-uc-unlimited-hf",
            "method": "SeleniumBase UC ONLY - unlimited",
            "hf_spaces": "Ping every 24h via cron-job.org to keep alive (sleeps after 48h)",
            "note": "Use /cron for ultra-lightweight plain text (50ms)"
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
        },
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@app.get("/status")
async def status_endpoint(request: Request):
    uptime = int(time.time() - START_TIME)
    return {
        "service": "perchance-solver",
        "status": "ok",
        "version": "3.0.0-selenium-uc-unlimited-hf",
        "memory": "800MB-1GB (SeleniumBase UC ONLY) - HF Spaces 16GB",
        "uptime_seconds": uptime,
        "uptime_human": f"{uptime//3600}h {(uptime%3600)//60}m {uptime%60}s",
        "ping_count": PING_COUNT["count"],
        "last_cron": PING_COUNT["last_cron"],
        "last_source": PING_COUNT["last_source"],
        "last_user_agent": PING_COUNT["last_ua"],
        "method": "SeleniumBase UC ONLY unlimited - tested working in E2B sandbox",
        "proof": "bid 0231e07d3b025b5a0f13de1e82358c54 userKey f0f66dce... via SB UC, adCode 24bad67d... via curl_cffi",
        "hf_spaces": {
            "hardware": "CPU Basic 2 vCPU, 16GB RAM - fits SeleniumBase 800MB",
            "sleep": "Sleeps after 48h, ping every 24h via cron-job.org",
            "setup": "cron-job.org → https://YOURSPACE.hf.space/cron → every 24h",
            "note": "Docker SDK Paid as of July 2026, but existing Spaces + Gradio/Streamlit still work. Use Gradio SDK."
        },
        "solver": {
            "sitekey": "0x4AAAAAAAA8g8NphwaSOT59",
            "page": "https://image-generation.perchance.org/embed",
            "method": "SeleniumBase UC Mode ONLY - UNLIMITED",
            "endpoints": ["/solve", "/generate", "/v1"]
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.post("/solve")
async def solve_turnstile(req: SolveRequest = SolveRequest()):
    """Solve Turnstile via SeleniumBase UC ONLY and return fresh userKey (64 hex, valid ~30s, IP-bound)"""
    try:
        result = await get_user_key_via_seleniumbase()
        if not result:
            raise HTTPException(status_code=500, detail="Failed to solve Turnstile via SeleniumBase UC")
        
        return {
            "status": "success",
            "userKey": result["userKey"],
            "browserId": result["browserId"],
            "method": result["method"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "expires_in": 30,
            "memory": "800MB SeleniumBase UC ONLY - HF Spaces 16GB",
            "unlimited": True,
            "note": "userKey is IP-bound to solver's IP, must generate via solver or same IP"
        }
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[Solver] /solve failed: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"Solve failed: {str(e)} {tb[:1000]}")

@app.post("/generate")
async def generate_image(req: GenerateRequest):
    """Full generation: solve Turnstile via SeleniumBase UC ONLY + generate via curl_cffi + download"""
    try:
        ad_code = await get_ad_code_via_curl_cffi()
        if not ad_code:
            print("[Solver] Warning: ad_code empty, trying anyway")
        
        solve_result = await get_user_key_via_seleniumbase()
        if not solve_result:
            raise HTTPException(status_code=500, detail="Failed to get userKey via SeleniumBase UC")
        
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
            "method": "seleniumbase-uc-unlimited + curl_cffi - HF Spaces 16GB",
            "unlimited": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[Solver] /generate failed: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"Generate failed: {str(e)} {tb[:2000]}")

@app.post("/v1")
async def flaresolverr_compatible(req: FlareSolverrRequest):
    """FlareSolverr-compatible API - but using SeleniumBase UC for Perchance"""
    try:
        # For generic FlareSolverr compat, we still use SeleniumBase UC
        from seleniumbase import SB
        import glob

        chromium_candidates = glob.glob("/home/user/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")
        chromium_candidates += ["/usr/bin/chromium", "/usr/bin/google-chrome"]
        chromium_path = None
        for cand in chromium_candidates:
            if os.path.exists(cand):
                chromium_path = cand
                break

        def _run_sync():
            with SB(uc=True, headless=True, chromium_arg="--no-sandbox --disable-gpu", binary_location=chromium_path) as sb:
                sb.open(req.url)
                sb.sleep(5)
                cookies = sb.execute_script("return document.cookie")
                ua = sb.execute_script("return navigator.userAgent")
                html = sb.get_page_source()[:10000]
                # Parse cookies to FlareSolverr format
                flare_cookies = []
                for c in cookies.split(';'):
                    if '=' in c:
                        k,v = c.strip().split('=',1)
                        flare_cookies.append({"name": k, "value": v, "domain": ".perchance.org"})
                return {"cookies": flare_cookies, "ua": ua, "html": html}

        result = await asyncio.to_thread(_run_sync)

        return {
            "status": "ok",
            "message": "Challenge solved (SeleniumBase UC ONLY unlimited - HF Spaces)",
            "solution": {
                "url": req.url,
                "status": 200,
                "cookies": result["cookies"],
                "userAgent": result["ua"],
                "response": result["html"],
                "headers": {}
            },
            "startTimestamp": int(time.time()*1000),
            "endTimestamp": int(time.time()*1000),
            "version": "3.0.0-selenium-uc-unlimited-hf"
        }

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[FlareSolverr API] Error: {e} {tb[:1000]}")
        raise HTTPException(status_code=500, detail=f"FlareSolverr compat failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", os.getenv("SPACE_PORT", "8000")))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting Perchance Solver (SeleniumBase UC ONLY Unlimited - HF Spaces 16GB) on {host}:{port}")
    uvicorn.run("solver:app", host=host, port=port, log_level="info")
