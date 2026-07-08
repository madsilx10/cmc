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
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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

        if len(e_lines) < 2:
            print(f"[!] Akun #{i+1}: email.txt format salah, skip")
            continue
        if len(w_lines) < 1:
            print(f"[!] Akun #{i+1}: wallet.txt kosong, skip")
            continue
        if len(a_lines) < 2:
            print(f"[!] Akun #{i+1}: account.txt format salah, skip")
            continue

        accounts.append({
            "email":      e_lines[0],
            "password":   e_lines[1],
            "wallet":     w_lines[0],
            "auth_token": a_lines[0],
            "ct0":        a_lines[1],
        })
    return accounts

# ── TWITTER (Selenium Bypass Anti-Ghost & Anti-Stuck) ───────────────────────
def get_x_headers(auth_token: str, ct0: str) -> dict:
    return {
        "cookie": f"auth_token={auth_token}; ct0={ct0}",
        "x-csrf-token": ct0,
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "referer": f"https://x.com/{FOLLOW_TARGET}",
        "origin": "https://x.com",
    }

async def x_get_user_id(auth_token: str, ct0: str, screen_name: str) -> Optional[str]:
    from urllib.parse import urlencode
    headers = get_x_headers(auth_token, ct0)
    variables = json.dumps({"screen_name": screen_name, "withGrokTranslatedBio": True})
    features = json.dumps({
        "hidden_profile_subscriptions_enabled": True,
        "profile_label_improvements_pcf_label_in_post_enabled": True,
        "responsive_web_profile_redirect_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
    })
    field_toggles = json.dumps({"withAuxiliaryUserLabels": True})
    gql_id = "2qvSHpkWTMS9i0zJAwDNiA"
    params = urlencode({"variables": variables, "features": features, "fieldToggles": field_toggles})
    url = f"https://x.com/i/api/graphql/{gql_id}/UserByScreenName?{params}"
    try:
        async with AsyncSession(impersonate="chrome116") as client:
            r = await client.get(url, headers=headers)
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
            r = await client.post(f"https://x.com/i/api/1.1/friendships/create.json?user_id={user_id}", headers=headers)
            if r.status_code in [200, 403]:
                print(f"  ✅ Follow @{FOLLOW_TARGET} aman")
                return True
            return False
    except Exception:
        return False

async def x_repost(auth_token: str, ct0: str) -> bool:
    """Repost via Selenium Headless yang dioptimalkan agar tidak mudah stuck."""
    print("  [*] Membuka browser Selenium untuk Repost asli...")
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-setuid-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    # Sembunyikan identitas otomasi
    options.add_argument('--blink-settings=imagesEnabled=false') # skip loading gambar biar cepat
    options.add_argument('--user-agent=Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36')
    
    service = Service(executable_path='/data/data/com.termux/files/usr/bin/chromedriver')
    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=options)
        # Set limit loading halaman biar gak stuck selamanya
        driver.set_page_load_timeout(25)
        
        # Inject cookie
        driver.get('https://x.com')
        driver.add_cookie({'name': 'auth_token', 'value': auth_token, 'domain': '.x.com'})
        driver.add_cookie({'name': 'ct0', 'value': ct0, 'domain': '.x.com'})
        
        # Buka tweet target
        tweet_url = f"https://x.com/i/web/status/{TWEET_ID}"
        try:
            driver.get(tweet_url)
        except Exception:
            # Tetap lanjut jika timeout saat memuat elemen luar (komentar/iklan)
            pass
            
        await asyncio.sleep(4)
        
        # Cek apakah halaman minta login ulang atau diblokir
        if "login" in driver.current_url.lower():
            print("  [X] Akun ter-logout otomatis oleh X (auth_token kadaluarsa).")
            return False

        wait = WebDriverWait(driver, 15)
        
        # Cek kondisi tombol repost
        try:
            unretweet = driver.find_elements(By.XPATH, '//button[@data-testid="unretweet"]')
            if unretweet:
                print("  ⏭️  Tweet sudah pernah di-repost sebelumnya, skip.")
                return True
        except:
            pass

        # Klik tombol Repost pertama
        repost_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[@data-testid="retweet"]')))
        repost_btn.click()
        await asyncio.sleep(1.5)
        
        # Klik menu konfirmasi pop-up "Repost"
        confirm_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//div[@data-testid="retweetConfirm"] | //span[contains(text(),"Repost")]')))
        confirm_btn.click()
        
        print("  ✅ [Selenium] Repost terkonfirmasi sukses dan ter-publish!")
        await asyncio.sleep(2)
        return True
    except Exception as e:
        print(f"  [X] Gagal eksekusi repost: {str(e)[:100]}")
        return False
    finally:
        if driver:
            try: driver.quit()
            except: pass

def load_waf_token() -> str:
    p = Path("waf.txt")
    if not p.exists(): return ""
    return p.read_text().strip()

def load_bearers() -> list:
    p = Path("bearer.txt")
    if not p.exists() or p.read_text().strip() == "":
        return []
    return [l.strip() for l in p.read_text().strip().splitlines() if l.strip()]

# ── CMC ──────────────────────────────────────────────────────────────────────
WAF_TOKEN = ""
BEARER_TOKEN = ""

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
            if r.status_code == 200:
                return r.json().get("data", {}).get("token")
            return None
        except Exception:
            return None

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
        except Exception:
            return False

async def cmc_join(token: str) -> bool:
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(f"{CMC_BASE}/quest/v3/quest/detail-page/join", headers=cmc_headers(token), json={"questId": QUEST_ID})
            return r.json().get("data", {}).get("join", False) if r.status_code == 200 else False
        except Exception:
            return False

# ── MAIN ─────────────────────────────────────────────────────────────────────
async def run_account(idx: int, acc: dict, state: dict, bearer: str = ""):
    email = acc["email"]
    print(f"\n{'='*50}\n[Akun {idx+1}] {email}\n{'='*50}")

    if is_done(state, email, "follow"):
        print("[1] ⏭️  Follow sudah selesai, skip")
    else:
        print("[1] Follow @LitecoinVM di X...")
        if await x_follow(acc["auth_token"], acc["ct0"]): mark_done(state, email, "follow")
        await sleep()

    if is_done(state, email, "repost"):
        print("[2] ⏭️  Repost sudah selesai, skip")
    else:
        print("[2] Repost tweet via Selenium...")
        if await x_repost(acc["auth_token"], acc["ct0"]): mark_done(state, email, "repost")
        await sleep()

    print("[3] CMC token...")
    token = bearer.replace("Bearer ", "").strip() if bearer else await cmc_login(acc["email"], acc["password"])
    if not token:
        print("  ⛔ Skip akun ini (token gagal)")
        return
    await sleep()

    for task_name, task_id, ext in [("wallet", TASK_WALLET, acc["wallet"]), ("task_follow", TASK_FOLLOW, None), ("task_repost", TASK_REPOST, None), ("visit", TASK_VISIT, None)]:
        print(f"[*] Verify {task_name}...")
        if is_done(state, email, task_name):
            print(f"  ⏭️  {task_name} sudah selesai, skip")
        else:
            if await cmc_verify(token, task_id, ext): mark_done(state, email, task_name)
        await sleep()

    print("[8] Join quest...")
    await cmc_join(token)

def select_accounts(accounts):
    print(f"\n[*] Total akun: {len(accounts)}\nPilih mode:\n  1. Jalankan 1 akun\n  2. Jalankan semua\n  3. Mulai dari akun ke-X")
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
            t = random.uniform(10, 20)
            print(f"\n⏳ Jeda antar akun {t:.0f}s...")
            await asyncio.sleep(t)
    print(f"\n[*] Selesai!")

if __name__ == "__main__":
    asyncio.run(main())
