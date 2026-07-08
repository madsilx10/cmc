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
        
        # Grab semua cookies
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

# ── TWITTER (httpx + GraphQL) ────────────────────────────────────────────────
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
        "sec-ch-ua": '"Not)A;Brand";v="24", "Chromium";v="116"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }

async def x_get_user_id(auth_token: str, ct0: str, screen_name: str) -> Optional[str]:
    from urllib.parse import urlencode
    headers = get_x_headers(auth_token, ct0)
    variables = json.dumps({"screen_name": screen_name, "withGrokTranslatedBio": True})
    features = json.dumps({
        "hidden_profile_subscriptions_enabled": True,
        "profile_label_improvements_pcf_label_in_post_enabled": True,
        "responsive_web_profile_redirect_enabled": False,
        "rweb_tipjar_consumption_enabled": False,
        "verified_phone_label_enabled": False,
        "subscriptions_verification_info_is_identity_verified_enabled": True,
        "subscriptions_verification_info_verified_since_enabled": True,
        "highlights_tweets_tab_ui_enabled": True,
        "responsive_web_twitter_article_notes_tab_enabled": True,
        "subscriptions_feature_can_gift_premium": True,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
    })
    field_toggles = json.dumps({"withAuxiliaryUserLabels": True})
    gql_id = "2qvSHpkWTMS9i0zJAwDNiA"
    params = urlencode({"variables": variables, "features": features, "fieldToggles": field_toggles})
    url = f"https://x.com/i/api/graphql/{gql_id}/UserByScreenName?{params}"
    try:
        async with AsyncSession(impersonate="chrome116") as client:
            r = await client.get(url, headers=headers)
            data = r.json()
            rest_id = data.get("data", {}).get("user", {}).get("result", {}).get("rest_id")
            return rest_id
    except Exception as e:
        print(f"  [X] Lookup user id error: {e}")
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
            r = await client.post(
                f"https://x.com/i/api/1.1/friendships/create.json?user_id={user_id}",
                headers=headers,
            )
            if r.status_code == 403:
                print(f"  ⏭️  Sudah follow @{FOLLOW_TARGET}, skip")
                return True
            if r.status_code == 200:
                print(f"  ✅ Follow @{FOLLOW_TARGET} berhasil")
                return True
            print(f"  [X] Follow gagal: {r.status_code} {r.text[:150]}")
            return False
    except Exception as e:
        print(f"  [X] Follow error: {e}")
        return False

async def x_repost(auth_token: str, ct0: str) -> bool:
    from urllib.parse import urlencode
    headers = get_x_headers(auth_token, ct0)
    
    try:
        async with AsyncSession(impersonate="chrome116") as client:
            # ── LANGKAH 1: SIMULASI BUKA TWEET TARGET (Nge-GET dulu biar gak di-ghosting X) ──
            tweet_vars = json.dumps({
                "tweetId": str(TWEET_ID),
                "withCommunity": False,
                "includePromotedContent": False,
                "withVoice": False
            })
            tweet_feats = json.dumps({
                "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                "responsive_web_graphql_timeline_navigation_enabled": True,
                "responsive_web_graphql_exclude_directive_enabled": True,
                "verified_phone_label_enabled": False,
                "creator_subscriptions_tweet_preview_api_enabled": True,
                "longform_notetweets_consumption_enabled": True,
                "tweet_awards_web_tipping_enabled": False,
                "freedom_of_speech_not_reach_fetch_enabled": True,
                "standardized_nudges_misinfo": True,
                "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                "rweb_video_timestamps_enabled": True,
                "longform_notetweets_rich_text_read_enabled": True,
                "longform_notetweets_inline_media_create_enabled": True
            })
            
            view_params = urlencode({"variables": tweet_vars, "features": tweet_feats})
            # Pakai endpoint GraphQL TweetResultByRestId bawaan browser asli
            await client.get(
                f"https://x.com/i/api/graphql/064as96ZfCHYyvba0wY3dg/TweetResultByRestId?{view_params}",
                headers=headers
            )
            
            # Beri jeda organik seolah orang lagi baca isi tweet sebentar
            await asyncio.sleep(random.uniform(2.5, 4.0))

            # ── LANGKAH 2: EKSEKUSI REPOST TWEET ──
            headers["content-type"] = "application/json"
            repost_payload = {
                "variables": {
                    "tweet_id": str(TWEET_ID),
                    "dark_request": False
                },
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
            )
            
            if r.status_code == 200:
                data = r.json()
                errors = data.get("errors", [])

                for err in errors:
                    if err.get("code") == 327:
                        print(f"  ⏭️  Sudah repost tweet, skip")
                        return True
                    if err.get("code") == 344:
                        print(f"  [X] Rate limit Twitter, tunggu 24 jam")
                        return False

                retweet_result = data.get("data", {}).get("create_retweet")
                if retweet_result:
                    print(f"  ✅ Repost tweet beneran tembus!")
                    return True

                print(f"  [X] Repost gagal (ditolak backend X): {json.dumps(data)[:200]}")
                return False
            if r.status_code == 404:
                print(f"  [X] Repost 404 — endpoint/tweet gak valid.")
                return False
            print(f"  [X] Repost gagal: {r.status_code} {r.text[:200]}")
            return False
    except Exception as e:
        print(f"  [X] Repost error: {e}")
        return False

def load_waf_token() -> str:
    p = Path("waf.txt")
    if not p.exists():
        print("[!] waf.txt tidak ditemukan")
        return ""
    return p.read_text().strip()

def load_bearers() -> list:
    p = Path("bearer.txt")
    if not p.exists() or p.read_text().strip() == "":
        print("[!] bearer.txt kosong atau gak ada")
        print("[1] Grab bearer otomatis (pakai Selenium)")
        print("[2] Skip (manual nanti)")
        choice = input("Pilih (1/2): ").strip()
        if choice == "1":
            bearer = grab_bearer_selenium()
            if bearer:
                p.write_text(bearer)
                print("[✓] Bearer disimpan ke bearer.txt")
                return [bearer]
        return []
    return [l.strip() for l in p.read_text().strip().splitlines() if l.strip()]

# ── CMC ──────────────────────────────────────────────────────────────────────
WAF_TOKEN = ""
BEARER_TOKEN = ""

def get_cookie_val(cookie_str: str, key: str) -> str:
    for part in cookie_str.split(";"):
        part = part.strip()
        if part.startswith(key + "="):
            return part[len(key)+1:]
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
        "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": "https://coinmarketcap.com",
        "referer": "https://coinmarketcap.com/",
        "platform": "Mobile Web",
        "sec-ch-ua": '"Not)A;Brand";v="24", "Chromium";v="116"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
        "x-request-id": str(uuid.uuid4()).replace("-", ""),
    }
    if WAF_TOKEN:
        h["cookie"] = strip_auth_from_cookie(WAF_TOKEN)
    if csrf:
        h["x-csrf-token"] = csrf
    if fvideo:
        h["fvideo-id"] = fvideo
    bearer = token or BEARER_TOKEN
    if bearer:
        jwt = bearer.replace("Bearer ", "").replace("Bearer", "").strip()
        h["authorization"] = f"Bearer {jwt}"
    return h

async def cmc_login(email: str, password: str) -> Optional[str]:
    payload = {
        "email": email,
        "platform": "web",
        "shaPassword": sha512(password),
        "signature": None,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(
                f"{CMC_BASE}/auth/v4/user/login",
                headers=cmc_headers(),
                json=payload,
            )
            if r.status_code == 200:
                data = r.json()
                token = data.get("data", {}).get("token")
                if token:
                    print(f"  ✅ Login CMC berhasil")
                    return token
                print(f"  [X] Token kosong. Response: {json.dumps(data)[:300]}")
                return None
            if r.status_code == 202:
                print(f"  [X] CMC 202 — WAF masih nge-block. Cek waf.txt")
                return None
            print(f"  [X] Login CMC gagal: {r.status_code}. Body: {r.text[:300]}")
            return None
        except Exception as e:
            print(f"  [X] Login error: {e}")
            return None

async def cmc_verify(token: str, task_id: str, external_id: str = None) -> bool:
    payload = {"questId": QUEST_ID, "taskId": task_id}
    if external_id:
        payload["externalId"] = external_id
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(
                f"{CMC_BASE}/quest/v3/quest/task/verify",
                headers=cmc_headers(token),
                json=payload,
            )
            if r.status_code == 200:
                data = r.json()
                err = data.get("status", {}).get("error_code", "")
                msg = data.get("status", {}).get("error_message", "")
                print(f"    [Verify Response] code={err}, msg={msg}")
                if msg == "SUCCESS":
                    print(f"    ✓ Success!")
                    return True
                if str(err) == "60005":
                    print(f"    ✓ Already verified (code 60005)")
                    return True
                print(f"    Response: {json.dumps(data, indent=2)[:500]}")
                return False
            print(f"  [X] Verify gagal: {r.status_code}. Body: {r.text[:300]}")
            return False
        except Exception as e:
            print(f"  [X] Verify error: {e}")
            return False

async def cmc_join(token: str) -> bool:
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(
                f"{CMC_BASE}/quest/v3/quest/detail-page/join",
                headers=cmc_headers(token),
                json={"questId": QUEST_ID},
            )
            if r.status_code == 200:
                if r.json().get("data", {}).get("join", False):
                    print(f"  ✅ Join quest berhasil")
                    return True
            print(f"  [X] Join quest gagal: {r.status_code}")
            return False
        except Exception as e:
            print(f"  [X] Join error: {e}")
            return False

# ── MAIN ─────────────────────────────────────────────────────────────────────
async def run_account(idx: int, acc: dict, state: dict, bearer: str = ""):
    email = acc["email"]
    print(f"\n{'='*50}")
    print(f"[Akun {idx+1}] {email}")
    print(f"{'='*50}")

    if is_done(state, email, "follow"):
        print("[1] ⏭️  Follow sudah selesai, skip")
    else:
        print("[1] Follow @LitecoinVM di X...")
        ok = await x_follow(acc["auth_token"], acc["ct0"])
        if ok:
            mark_done(state, email, "follow")
        await sleep()

    # Delay lebih lama sebelum repost
    delay = random.uniform(15, 25)
    print(f"⏳ Delay {delay:.0f}s sebelum repost...")
    await asyncio.sleep(delay)

    if is_done(state, email, "repost"):
        print("[2] ⏭️  Repost sudah selesai, skip")
    else:
        print("[2] Repost tweet...")
        ok = await x_repost(acc["auth_token"], acc["ct0"])
        if ok:
            mark_done(state, email, "repost")
        await sleep()

    print("[3] CMC token...")
    if bearer:
        token = bearer.replace("Bearer ", "").strip()
        print(f"  ✅ Pakai bearer dari bearer.txt")
    else:
        token = await cmc_login(acc["email"], acc["password"])
    if not token:
        print("  ⛔ Skip akun ini (token gagal)")
        return
    await sleep()

    print("[4] Verify wallet address...")
    if is_done(state, email, "wallet"):
        print("  ⏭️  Task wallet sudah selesai, skip")
    else:
        ok = await cmc_verify(token, TASK_WALLET, acc["wallet"])
        if ok:
            mark_done(state, email, "wallet")
        print(f"  {'✅' if ok else '❌'} Task wallet")
    await sleep()

    print("[5] Verify task follow...")
    if is_done(state, email, "task_follow"):
        print("  ⏭️  Task follow sudah selesai, skip")
    else:
        ok = await cmc_verify(token, TASK_FOLLOW)
        if ok:
            mark_done(state, email, "task_follow")
        print(f"  {'✅' if ok else '❌'} Task follow")
    await sleep()

    print("[6] Verify task repost...")
    if is_done(state, email, "task_repost"):
        print("  ⏭️  Task repost sudah selesai, skip")
    else:
        ok = await cmc_verify(token, TASK_REPOST)
        if ok:
            mark_done(state, email, "task_repost")
        print(f"  {'✅' if ok else '❌'} Task repost")
    await sleep()

    print("[7] Verify task visit web...")
    if is_done(state, email, "visit"):
        print("  ⏭️  Task visit sudah selesai, skip")
    else:
        ok = await cmc_verify(token, TASK_VISIT)
        if ok:
            mark_done(state, email, "visit")
        print(f"  {'✅' if ok else '❌'} Task visit web")
    await sleep()

    print("[8] Join quest...")
    await cmc_join(token)

def select_accounts(accounts):
    print(f"\n[*] Total akun ter-load: {len(accounts)}")
    print("Pilih mode:")
    print("  1. Jalankan 1 akun tertentu")
    print("  2. Jalankan semua akun")
    print("  3. Jalankan dari akun ke-X sampai akhir")
    choice = input("Pilihan (1/2/3): ").strip()

    if choice == "1":
        while True:
            try:
                n = int(input(f"Nomor akun (1-{len(accounts)}): ").strip())
                if 1 <= n <= len(accounts):
                    return [(n - 1, accounts[n - 1])]
                print(f"[!] Masukkan angka 1-{len(accounts)}")
            except ValueError:
                print("[!] Input harus angka")
    elif choice == "3":
        while True:
            try:
                n = int(input(f"Mulai dari akun ke- (1-{len(accounts)}): ").strip())
                if 1 <= n <= len(accounts):
                    return [(i, acc) for i, acc in enumerate(accounts) if i >= n - 1]
                print(f"[!] Masukkan angka 1-{len(accounts)}")
            except ValueError:
                print("[!] Input harus angka")
    else:
        return list(enumerate(accounts))

async def main():
    global WAF_TOKEN, BEARER_TOKEN
    WAF_TOKEN = load_waf_token()
    bearers = load_bearers()
    if WAF_TOKEN:
        print(f"[*] WAF token loaded ({WAF_TOKEN[:20]}...)")
    if bearers:
        print(f"[*] {len(bearers)} bearer token loaded")

    accounts = load_accounts()
    if not accounts:
        print("[!] Tidak ada akun yang berhasil di-load")
        sys.exit(1)

    state = load_state()
    selected = select_accounts(accounts)
    print(f"[*] Akan menjalankan {len(selected)} akun")

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
