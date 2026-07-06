import httpx
import hashlib
import asyncio
import random
import sys
import time
import json
import urllib.parse
from pathlib import Path

# ── CONFIG ──────────────────────────────────────────────────────────────────
QUEST_ID  = "6a481677582fb7144ae0798c"
TWEET_URL = "https://x.com/LitecoinVM/status/2044460314645979226"
TWEET_ID  = "2044460314645979226"
FOLLOW_TARGET = "LitecoinVM"  # Twitter username

TASK_WALLET  = "617a3413-caf9-4cff-b584-2380440e5317"
TASK_FOLLOW  = "87c006b3-c8e6-4579-9de4-6f1a69f89bdc"
TASK_REPOST  = "3f20ee63-1bbd-4a17-9d28-7ed636f182bf"
TASK_VISIT   = "a6ca400d-186a-480a-bbd1-237dd9066f98"

CMC_BASE = "https://api.coinmarketcap.com"

DELAY_MIN = 3
DELAY_MAX = 7

# ── HELPERS ─────────────────────────────────────────────────────────────────
def sha512(text: str) -> str:
    return hashlib.sha512(text.encode()).hexdigest()

def sleep():
    t = random.uniform(DELAY_MIN, DELAY_MAX)
    print(f"  💤 sleep {t:.1f}s")
    time.sleep(t)

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

# ── TWITTER ──────────────────────────────────────────────────────────────────
_BEARER_CACHE = None

def fetch_bearer_token() -> str:
    """Ambil Bearer token dari JS bundle Twitter secara otomatis"""
    global _BEARER_CACHE
    if _BEARER_CACHE:
        return _BEARER_CACHE

    fallback = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLiK7wRl8Z8MNs6LQzGdHMlXEBl"
    try:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        with httpx.Client(timeout=20, headers={"user-agent": ua}) as client:
            r = client.get("https://x.com/")
            # Cari URL JS main bundle
            import re
            js_urls = re.findall(r'src="(https://abs\.twimg\.com/responsive-web/client-web/main\.[^"]+\.js)"', r.text)
            if not js_urls:
                js_urls = re.findall(r'"(https://abs\.twimg\.com/responsive-web/client-web/main\.[^"]+\.js)"', r.text)
            if not js_urls:
                print("  [!] Tidak bisa temukan JS bundle, pakai Bearer fallback")
                return fallback

            js_r = client.get(js_urls[0])
            match = re.search(r'Bearer (AAAAAAAAAAAAAAAAAAAAAA[A-Za-z0-9%]+)', js_r.text)
            if match:
                token = "Bearer " + match.group(1)
                # strip prefix karena nanti ditambah di header
                _BEARER_CACHE = match.group(1)
                print(f"  [✓] Bearer token berhasil di-fetch dari JS bundle")
                return _BEARER_CACHE
    except Exception as e:
        print(f"  [!] Gagal fetch Bearer token: {e}")

    return fallback

def get_x_headers(auth_token: str, ct0: str) -> dict:
    bearer = fetch_bearer_token()
    return {
        "authorization": f"Bearer {bearer}",
        "cookie": f"auth_token={auth_token}; ct0={ct0}",
        "x-csrf-token": ct0,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "referer": "https://x.com/",
        "origin": "https://x.com",
    }

GQL_FEATURES_USER = json.dumps({
    "hidden_profile_likes_enabled": True,
    "hidden_profile_subscriptions_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
})

def x_get_user_info(client, headers, username: str):
    """Lookup user via GraphQL — return (rest_id, is_following)"""
    params = {
        "variables": json.dumps({"screen_name": username, "withSafetyModeUserFields": True}),
        "features": GQL_FEATURES_USER,
    }
    r = client.get(
        "https://x.com/i/api/graphql/k5Ndt2-Y-1hbz2BEHRpxHw/UserByScreenName",
        headers=headers,
        params=params,
    )
    if r.status_code != 200:
        print(f"  [X] Gagal lookup user: {r.status_code} {r.text[:150]}")
        return None, False
    try:
        result = r.json()["data"]["user"]["result"]
        rest_id = result["rest_id"]
        is_following = result.get("legacy", {}).get("following", False)
        return rest_id, is_following
    except (KeyError, TypeError) as e:
        print(f"  [X] Parse user info gagal: {e}")
        return None, False

def x_follow(auth_token: str, ct0: str) -> bool:
    headers = get_x_headers(auth_token, ct0)
    with httpx.Client(timeout=30) as client:
        target_id, is_following = x_get_user_info(client, headers, FOLLOW_TARGET)
        if not target_id:
            return False

        if is_following:
            print(f"  ⏭️  Sudah follow @{FOLLOW_TARGET}, skip")
            return True

        r = client.post(
            "https://x.com/i/api/graphql/wlUWOFMsqeJmDlOGDoXU9Q/FollowUser",
            headers={**headers, "content-type": "application/json"},
            json={
                "variables": {"userId": target_id, "includePromotedContent": False},
                "features": json.loads(GQL_FEATURES_USER),
            },
        )
        if r.status_code == 200:
            print(f"  ✅ Follow @{FOLLOW_TARGET} berhasil")
            return True
        print(f"  [X] Follow gagal: {r.status_code} {r.text[:150]}")
        return False

def x_repost(auth_token: str, ct0: str) -> bool:
    headers = get_x_headers(auth_token, ct0)
    with httpx.Client(timeout=30) as client:
        r = client.post(
            "https://x.com/i/api/graphql/ojPdsZsimiJrUGLR1sjUtA/CreateRetweet",
            headers={**headers, "content-type": "application/json"},
            json={
                "variables": {"tweet_id": TWEET_ID, "dark_request": False},
                "queryId": "ojPdsZsimiJrUGLR1sjUtA",
            },
        )
        if r.status_code == 200:
            print(f"  ✅ Repost tweet berhasil")
            return True
        if r.status_code == 404:
            print(f"  [X] Repost gagal 404 — tweet tidak ditemukan atau dihapus")
            return False
        print(f"  [X] Repost gagal: {r.status_code} {r.text[:150]}")
        return False

# ── CMC ──────────────────────────────────────────────────────────────────────
def cmc_headers(token: str = None) -> dict:
    h = {
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "content-type": "application/json",
        "origin": "https://coinmarketcap.com",
        "referer": "https://coinmarketcap.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "platform": "web",
        "x-request-id": str(random.randint(100000, 999999)),
    }
    if token:
        h["authorization"] = f"Bearer {token}"
    return h

def cmc_login(email: str, password: str) -> str | None:
    payload = {
        "email": email,
        "platform": "web",
        "shaPassword": sha512(password),
        "signature": None,
    }
    with httpx.Client(timeout=30) as client:
        r = client.post(
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
            print(f"  [X] Login CMC: response 200 tapi token kosong")
            print(f"  [!] Response: {r.text[:300]}")
            return None

        elif r.status_code == 202:
            body = r.text.strip()
            if body:
                try:
                    data = r.json()
                    token = data.get("data", {}).get("token")
                    if token:
                        print(f"  ✅ Login CMC berhasil (202 dengan token)")
                        return token
                    print(f"  ⚠️  CMC return 202, body: {body[:300]}")
                except Exception:
                    print(f"  ⚠️  CMC return 202, body non-JSON: {body[:300]}")
            else:
                print(f"  ⚠️  CMC return 202 body kosong — kemungkinan IP flagged atau perlu login manual dulu di browser")
            return None

        body = r.text.strip()
        print(f"  [X] Login CMC gagal: {r.status_code} {body[:300] if body else '(empty body)'}")
        return None

def cmc_verify(token: str, task_id: str, external_id: str = None) -> bool:
    payload = {"questId": QUEST_ID, "taskId": task_id}
    if external_id:
        payload["externalId"] = external_id

    with httpx.Client(timeout=30) as client:
        r = client.post(
            f"{CMC_BASE}/quest/v3/quest/task/verify",
            headers=cmc_headers(token),
            json=payload,
        )
        if r.status_code == 200:
            msg = r.json().get("status", {}).get("error_message", "")
            if msg == "SUCCESS":
                return True
        print(f"  [X] Verify task gagal ({task_id[:8]}...): {r.status_code} {r.text[:150]}")
        return False

def cmc_join(token: str) -> bool:
    with httpx.Client(timeout=30) as client:
        r = client.post(
            f"{CMC_BASE}/quest/v3/quest/detail-page/join",
            headers=cmc_headers(token),
            json={"questId": QUEST_ID},
        )
        if r.status_code == 200:
            joined = r.json().get("data", {}).get("join", False)
            if joined:
                print(f"  ✅ Join quest berhasil")
                return True
        print(f"  [X] Join quest gagal: {r.status_code} {r.text[:150]}")
        return False

# ── MAIN ─────────────────────────────────────────────────────────────────────
def run_account(idx: int, acc: dict):
    print(f"\n{'='*50}")
    print(f"[Akun {idx+1}] {acc['email']}")
    print(f"{'='*50}")

    # Step 1: Follow di X
    print("[1] Follow @LitecoinVM di X...")
    x_follow(acc["auth_token"], acc["ct0"])
    sleep()

    # Step 2: Repost di X
    print("[2] Repost tweet...")
    x_repost(acc["auth_token"], acc["ct0"])
    sleep()

    # Step 3: Login CMC
    print("[3] Login CMC...")
    token = cmc_login(acc["email"], acc["password"])
    if not token:
        print("  ⛔ Skip akun ini (login gagal)")
        return
    sleep()

    # Step 4: Verify wallet
    print("[4] Verify wallet address...")
    ok = cmc_verify(token, TASK_WALLET, acc["wallet"])
    print(f"  {'✅' if ok else '❌'} Task wallet")
    sleep()

    # Step 5: Verify follow
    print("[5] Verify task follow...")
    ok = cmc_verify(token, TASK_FOLLOW)
    print(f"  {'✅' if ok else '❌'} Task follow")
    sleep()

    # Step 6: Verify repost
    print("[6] Verify task repost...")
    ok = cmc_verify(token, TASK_REPOST)
    print(f"  {'✅' if ok else '❌'} Task repost")
    sleep()

    # Step 7: Verify visit web
    print("[7] Verify task visit web...")
    ok = cmc_verify(token, TASK_VISIT)
    print(f"  {'✅' if ok else '❌'} Task visit web")
    sleep()

    # Step 8: Join quest
    print("[8] Join quest...")
    cmc_join(token)

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

def main():
    accounts = load_accounts()
    if not accounts:
        print("[!] Tidak ada akun yang berhasil di-load")
        sys.exit(1)

    selected = select_accounts(accounts)
    print(f"[*] Akan menjalankan {len(selected)} akun")

    for n, (i, acc) in enumerate(selected):
        run_account(i, acc)
        if n < len(selected) - 1:
            t = random.uniform(10, 20)
            print(f"\n⏳ Jeda antar akun {t:.0f}s...")
            time.sleep(t)

    print(f"\n[*] Selesai!")

if __name__ == "__main__":
    main()
