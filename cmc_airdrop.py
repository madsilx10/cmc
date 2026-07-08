import httpx
import hashlib
import asyncio
import random
import sys
import time
import json
import uuid
from pathlib import Path
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from curl_cffi.requests import AsyncSession

def grab_bearer_selenium() -> str:
    """Grab Authorization bearer dari CMC pake Selenium."""
    print("\n[*] Membuka browser untuk grab bearer CMC...")
    
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-setuid-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--single-process')
    options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
    
    service = Service(executable_path='/data/data/com.termux/files/usr/bin/chromedriver')
    
    try:
        driver = webdriver.Chrome(service=service, options=options)
        driver.get('https://coinmarketcap.com/account/login')
        
        print("[*] Browser terbuka, login manual di browser... (buka screen termux yg menampilkan browser)")
        print("[*] Setelah login berhasil, tekan Enter di sini...")
        input()
        
        cookies = driver.get_cookies()
        for cookie in cookies:
            if cookie['name'] == 'Authorization':
                bearer = cookie['value']
                print(f"[✓] Bearer grabbed: {bearer[:30]}...")
                return bearer
        
        print("[!] Authorization cookie tidak ditemukan")
        return ""
        
    except Exception as e:
        print(f"[X] Selenium error: {e}")
        return ""
    finally:
        try:
            driver.quit()
        except:
            pass

# ── STATE TRACKER ─────────────────────────────────────────────────────────────
STATE_FILE = Path("done.json")

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def is_done(state: dict, email: str, task: str) -> bool:
    return state.get(email, {}).get(task, False)

def mark_done(state: dict, email: str, task: str):
    if email not in state:
        state[email] = {}
    state[email][task] = True
    save_state(state)

# ── CONFIG ──────────────────────────────────────────────────────────────────
QUEST_ID  = "6a481677582fb7144ae0798c"
TWEET_ID  = "2044460314645979226"
FOLLOW_TARGET = "LitecoinVM"

TASK_WALLET  = "617a3413-caf9-4cff-b584-2380440e5317"
TASK_FOLLOW  = "87c006b3-c8e6-4579-9de4-6f1a69f89bdc"
TASK_REPOST  = "3f20ee63-1bbd-4a17-9d28-7ed636f182bf"
TASK_VISIT   = "a6ca400d-186a-480a-bbd1-237dd9066f98"

CMC_BASE  = "https://api.coinmarketcap.com"
DELAY_MIN = 3
DELAY_MAX = 7

# ── HELPERS ──────────────────────────────────────────────────────────────────
def sha512(text: str) -> str:
    return hashlib.sha512(text.encode()).hexdigest()

async def sleep():
    t = random.uniform(DELAY_MIN, DELAY_MAX)
    print(f"  💤 sleep {t:.1f}s")
    await asyncio.sleep(t)

def load_accounts():
    emails_raw   = Path("email.txt").read_text().strip().split("\n\n")
    wallets_raw  = Path("wallet.txt").read_text().strip().split("\n\n")
    accounts_raw = Path("account.txt").read_text().strip().split("\n\n")

    accounts = []
    for i, (e_block, w_block, a_block) in enumerate(zip(emails_raw, wallets_raw, accounts_raw)):
        e_lines = [l.strip() for l in e_block.strip().splitlines() if l.strip()]
        w_lines = [l.strip() for l in w_block.strip().splitlines() if l.strip()]
        a_lines = [l.strip() for l in a_block.strip().splitlines() if l.strip()]

        if len(e_lines) < 2: continue
        if len(w_lines) < 1: continue
        if len(a_lines) < 2: continue

        accounts.append({
            "email":      e_lines[0],
            "password":   e_lines[1],
            "wallet":     w_lines[0],
            "auth_token": a_lines[0],
            "ct0":        a_lines[1],
        })
    return accounts

# ── TWITTER HANDSHAKE ENGINE (MENGGUNAKAN CHROME116) ─────────────────────────
def get_x_headers(auth_token: str, ct0: str) -> dict:
    return {
        "cookie": f"auth_token={auth_token}; ct0={ct0}",
        "x-csrf-token": ct0,
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "referer": "https://x.com/",
        "origin": "https://x.com",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
    }

async def x_get_user_id(auth_token: str, ct0: str, screen_name: str) -> Optional[str]:
    from urllib.parse import urlencode
    headers = get_x_headers(auth_token, ct0)
    variables = json.dumps({"screen_name": screen_name, "withGrokTranslatedBio": True})
    features = json.dumps({"hidden_profile_subscriptions_enabled": True, "profile_label_improvements_pcf_label_in_post_enabled": True, "responsive_web_profile_redirect_enabled": False, "responsive_web_graphql_timeline_navigation_enabled": True})
    field_toggles = json.dumps({"withAuxiliaryUserLabels": True})
    params = urlencode({"variables": variables, "features": features, "fieldToggles": field_toggles})
    url = f"https://x.com/i/api/graphql/2qvSHpkWTMS9i0zJAwDNiA/UserByScreenName?{params}"
    try:
        async with AsyncSession(impersonate="chrome116") as client:
            r = await client.get(url, headers=headers, timeout=15)
            return r.json().get("data", {}).get("user", {}).get("result", {}).get("rest_id")
    except Exception:
        return None

async def x_follow(auth_token: str, ct0: str) -> bool:
    headers = get_x_headers(auth_token, ct0)
    headers["content-type"] = "application/x-www-form-urlencoded"
    user_id = await x_get_user_id(auth_token, ct0, FOLLOW_TARGET)
    if not user_id:
        print(f"  [X] Gagal ambil user id @{FOLLOW_TARGET}")
        return False
    try:
        async with AsyncSession(impersonate="chrome116") as client:
            r = await client.post(f"https://x.com/i/api/1.1/friendships/create.json?user_id={user_id}", headers=headers, timeout=15)
            if r.status_code in [200, 403]:
                print(f"  ✅ Follow @{FOLLOW_TARGET} aman")
                return True
            return False
    except Exception:
        return False

async def x_repost(auth_token: str, ct0: str) -> bool:
    from urllib.parse import urlencode
    headers = get_x_headers(auth_token, ct0)
    
    try:
        async with AsyncSession(impersonate="chrome116") as client:
            # STEP 1: Ping Main Home Page untuk menyeimbangkan sesi cookie internal X
            await client.get("https://x.com/home", headers=headers, timeout=15)
            await asyncio.sleep(1.5)

            # STEP 2: Tarik detail Tweet (Simulasi Membaca secara real)
            tweet_vars = json.dumps({"tweetId": str(TWEET_ID), "withCommunity": False, "includePromotedContent": False, "withVoice": False})
            tweet_feats = json.dumps({
                "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                "responsive_web_graphql_timeline_navigation_enabled": True,
                "responsive_web_graphql_exclude_directive_enabled": True,
                "verified_phone_label_enabled": False,
                "creator_subscriptions_tweet_preview_api_enabled": True,
                "longform_notetweets_consumption_enabled": True,
                "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True
            })
            view_params = urlencode({"variables": tweet_vars, "features": tweet_feats})
            
            r_view = await client.get(f"https://x.com/i/api/graphql/064as96ZfCHYyvba0wY3dg/TweetResultByRestId?{view_params}", headers=headers, timeout=15)
            
            if r_view.status_code in [401, 403]:
                print("  [X] Gagal: Cookies Akun ini Invalid atau Expired.")
                return False
                
            await asyncio.sleep(random.uniform(2.5, 4.0))

            # STEP 3: Tembak Aksi Repost Utama
            repost_payload = {
                "variables": {"tweet_id": str(TWEET_ID), "dark_request": False},
                "features": {
                    "communities_web_enable_tweet_community_results_fetch": True,
                    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                    "view_counts_everywhere_api_enabled": True,
                    "longform_notetweets_consumption_enabled": True,
                    "responsive_web_graphql_timeline_navigation_enabled": True,
                    "responsive_web_graphql_exclude_directive_enabled": True,
                    "verified_phone_label_enabled": False,
                    "creator_subscriptions_tweet_preview_api_enabled": True,
                    "responsive_web_enhance_cards_enabled": False
                },
                "queryId": "mbRO74GrOvSfRcJnlMapnQ",
            }

            r = await client.post(
                "https://x.com/i/api/graphql/mbRO74GrOvSfRcJnlMapnQ/CreateRetweet",
                headers=headers,
                json=repost_payload,
                timeout=15
            )
            
            if r.status_code == 200:
                data = r.json()
                errors = data.get("errors", [])
                for err in errors:
                    if err.get("code") == 327:
                        print(f"  ⏭️  Sudah repost tweet, skip")
                        return True
                    if err.get("code") == 344:
                        print(f"  [X] Akun dibatasi/limit oleh X.")
                        return False

                if data.get("data", {}).get("create_retweet"):
                    print(f"  ✅ Repost asli tembus dan terverifikasi!")
                    return True

                print(f"  [X] Gagal: {json.dumps(data)[:120]}")
                return False
            print(f"  [X] HTTP Error {r.status_code}")
            return False
    except Exception as e:
        print(f"  [X] Sesi Error: {str(e)[:80]}")
        return False

# ── CMC SECTION ──────────────────────────────────────────────────────────────
WAF_TOKEN = ""
BEARER_TOKEN = ""

def load_waf_token() -> str:
    p = Path("waf.txt")
    return p.read_text().strip() if p.exists() else ""

def load_bearers() -> list:
    p = Path("bearer.txt")
    return [l.strip() for l in p.read_text().strip().splitlines() if l.strip()] if p.exists() else []

def get_cookie_val(cookie_str: str, key: str) -> str:
    for part in cookie_str.split(";"):
        part = part.strip()
        if part.startswith(key + "="): return part[len(key)+1:]
    return ""

def strip_auth_from_cookie(cookie_str: str) -> str:
    parts = [p.strip() for p in cookie_str.split(";")]
    parts = [p for p in parts if not p.lower().startswith("authorization=")]
    return "; ".join(parts)

def cmc_headers(token: str = None) -> dict:
    csrf = get_cookie_val(WAF_TOKEN, "x-csrf-token") if WAF_TOKEN else ""
    fvideo = get_cookie_val(WAF_TOKEN, "BNC_FV_KEY") if WAF_TOKEN else ""
    h = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://coinmarketcap.com",
        "referer": "https://coinmarketcap.com/",
        "platform": "Mobile Web",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
        "x-request-id": str(uuid.uuid4()).replace("-", ""),
    }
    if WAF_TOKEN: h["cookie"] = strip_auth_from_cookie(WAF_TOKEN)
    if csrf: h["x-csrf-token"] = csrf
    if fvideo: h["fvideo-id"] = fvideo
    bearer = token or BEARER_TOKEN
    if bearer:
        jwt = bearer.replace("Bearer ", "").replace("Bearer", "").strip()
        h["authorization"] = f"Bearer {jwt}"
    return h

async def cmc_login(email: str, password: str) -> Optional[str]:
    payload = {"email": email, "platform": "web", "shaPassword": sha512(password), "signature": None}
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(f"{CMC_BASE}/auth/v4/user/login", headers=cmc_headers(), json=payload)
            if r.status_code == 200: return r.json().get("data", {}).get("token")
            return None
        except Exception: return None

async def cmc_verify(token: str, task_id: str, external_id: str = None) -> bool:
    payload = {"questId": QUEST_ID, "taskId": task_id}
    if external_id: payload["externalId"] = external_id
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(f"{CMC_BASE}/quest/v3/quest/task/verify", headers=cmc_headers(token), json=payload)
            if r.status_code == 200:
                data = r.json()
                err = data.get("status", {}).get("error_code", "")
                msg = data.get("status", {}).get("error_message", "")
                print(f"    [Verify Response] msg={msg}")
                if msg == "SUCCESS" or str(err) == "60005": return True
            return False
        except Exception: return False

async def cmc_join(token: str) -> bool:
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(f"{CMC_BASE}/quest/v3/quest/detail-page/join", headers=cmc_headers(token), json={"questId": QUEST_ID})
            return r.json().get("data", {}).get("join", False) if r.status_code == 200 else False
        except Exception: return False

# ── ENGINE RUNNER ────────────────────────────────────────────────────────────
async def run_account(idx: int, acc: dict, state: dict, bearer: str = ""):
    email = acc["email"]
    print(f"\n{'='*50}\n[Akun {idx+1}] {email}\n{'='*50}")

    if is_done(state, email, "follow"):
        print("[1] ⏭️  Follow sudah selesai, skip")
    else:
        print("[1] Follow @LitecoinVM...")
        if await x_follow(acc["auth_token"], acc["ct0"]): mark_done(state, email, "follow")
        await sleep()

    if is_done(state, email, "repost"):
        print("[2] ⏭️  Repost sudah selesai, skip")
    else:
        print("[2] Repost via Handshake API...")
        if await x_repost(acc["auth_token"], acc["ct0"]): mark_done(state, email, "repost")
        await sleep()

    print("[3] Mendapatkan CMC token...")
    token = bearer.replace("Bearer ", "").strip() if bearer else await cmc_login(acc["email"], acc["password"])
    if not token:
        print("  ⛔ Skip akun (Login token CMC gagal)")
        return
    await sleep()

    for task_name, task_id, ext in [("wallet", TASK_WALLET, acc["wallet"]), ("task_follow", TASK_FOLLOW, None), ("task_repost", TASK_REPOST, None), ("visit", TASK_VISIT, None)]:
        print(f"[*] Verifikasi {task_name}...")
        if is_done(state, email, task_name):
            print(f"  ⏭️  {task_name} sudah beres, skip")
        else:
            if await cmc_verify(token, task_id, ext): mark_done(state, email, task_name)
        await sleep()

    print("[8] Mengikuti Quest...")
    await cmc_join(token)

def select_accounts(accounts):
    print(f"\n[*] Ter-load {len(accounts)} akun\nPilih mode:\n  1. Jalankan 1 akun\n  2. Jalankan semua\n  3. Mulai dari akun ke-X")
    choice = input("Pilihan (1/2/3): ").strip()
    if choice == "1":
        n = int(input(f"Nomor akun (1-{len(accounts)}): ").strip())
        return [(n - 1, accounts[n - 1])]
    elif choice == "3":
        n = int(input(f"Mulai dari akun ke- (1-{len(accounts)}): ").strip())
        return [(i, acc) for i, acc in enumerate(accounts) if i >= n - 1]
    return list(enumerate(accounts))

async def main():
    global WAF_TOKEN, BEARER_TOKEN
    WAF_TOKEN = load_waf_token()
    bearers = load_bearers()
    accounts = load_accounts()
    if not accounts: sys.exit(1)

    state = load_state()
    selected = select_accounts(accounts)

    for n, (i, acc) in enumerate(selected):
        bearer = bearers[i] if i < len(bearers) else ""
        await run_account(i, acc, state, bearer)
        if n < len(selected) - 1:
            t = random.uniform(10, 18)
            print(f"\n⏳ Jeda antar akun {t:.0f}s...")
            await asyncio.sleep(t)
    print(f"\n[*] Selesai semua!")

if __name__ == "__main__":
    asyncio.run(main())
