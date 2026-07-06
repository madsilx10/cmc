import httpx
import hashlib
import asyncio
import random
import sys
import time
import json
from pathlib import Path
from twikit import Client as TwikitClient

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

# ── TWITTER (Twikit) ─────────────────────────────────────────────────────────
async def get_twitter_client(auth_token: str, ct0: str) -> TwikitClient:
    client = TwikitClient(language="en-US")
    client.set_cookies({"auth_token": auth_token, "ct0": ct0})
    return client

async def x_follow(auth_token: str, ct0: str) -> bool:
    try:
        client = await get_twitter_client(auth_token, ct0)
        user = await client.get_user_by_screen_name(FOLLOW_TARGET)
        if user.following:
            print(f"  ⏭️  Sudah follow @{FOLLOW_TARGET}, skip")
            return True
        await user.follow()
        print(f"  ✅ Follow @{FOLLOW_TARGET} berhasil")
        return True
    except Exception as e:
        print(f"  [X] Follow gagal: {e}")
        return False

async def x_repost(auth_token: str, ct0: str) -> bool:
    try:
        client = await get_twitter_client(auth_token, ct0)
        tweet = await client.get_tweet_by_id(TWEET_ID)
        await tweet.retweet()
        print(f"  ✅ Repost tweet berhasil")
        return True
    except Exception as e:
        err = str(e)
        if "already retweeted" in err.lower() or "327" in err:
            print(f"  ⏭️  Sudah repost, skip")
            return True
        print(f"  [X] Repost gagal: {e}")
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
            token = r.json().get("data", {}).get("token")
            if token:
                print(f"  ✅ Login CMC berhasil")
                return token
            print(f"  [X] Token kosong. Response: {r.text[:300]}")
            return None

        elif r.status_code == 202:
            body = r.text.strip()
            if body:
                try:
                    token = r.json().get("data", {}).get("token")
                    if token:
                        print(f"  ✅ Login CMC berhasil (202)")
                        return token
                    print(f"  ⚠️  CMC 202, body: {body[:300]}")
                except Exception:
                    print(f"  ⚠️  CMC 202, non-JSON: {body[:300]}")
            else:
                print(f"  ⚠️  CMC 202 body kosong — IP flagged atau session expired")
            return None

        body = r.text.strip()
        print(f"  [X] Login CMC gagal: {r.status_code} {body[:300] if body else '(empty)'}")
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
            if r.json().get("status", {}).get("error_message") == "SUCCESS":
                return True
        print(f"  [X] Verify gagal ({task_id[:8]}...): {r.status_code} {r.text[:150]}")
        return False

def cmc_join(token: str) -> bool:
    with httpx.Client(timeout=30) as client:
        r = client.post(
            f"{CMC_BASE}/quest/v3/quest/detail-page/join",
            headers=cmc_headers(token),
            json={"questId": QUEST_ID},
        )
        if r.status_code == 200:
            if r.json().get("data", {}).get("join", False):
                print(f"  ✅ Join quest berhasil")
                return True
        print(f"  [X] Join quest gagal: {r.status_code} {r.text[:150]}")
        return False

# ── MAIN ─────────────────────────────────────────────────────────────────────
async def run_account(idx: int, acc: dict):
    print(f"\n{'='*50}")
    print(f"[Akun {idx+1}] {acc['email']}")
    print(f"{'='*50}")

    print("[1] Follow @LitecoinVM di X...")
    await x_follow(acc["auth_token"], acc["ct0"])
    await sleep()

    print("[2] Repost tweet...")
    await x_repost(acc["auth_token"], acc["ct0"])
    await sleep()

    print("[3] Login CMC...")
    token = cmc_login(acc["email"], acc["password"])
    if not token:
        print("  ⛔ Skip akun ini (login gagal)")
        return
    await sleep()

    print("[4] Verify wallet address...")
    ok = cmc_verify(token, TASK_WALLET, acc["wallet"])
    print(f"  {'✅' if ok else '❌'} Task wallet")
    await sleep()

    print("[5] Verify task follow...")
    ok = cmc_verify(token, TASK_FOLLOW)
    print(f"  {'✅' if ok else '❌'} Task follow")
    await sleep()

    print("[6] Verify task repost...")
    ok = cmc_verify(token, TASK_REPOST)
    print(f"  {'✅' if ok else '❌'} Task repost")
    await sleep()

    print("[7] Verify task visit web...")
    ok = cmc_verify(token, TASK_VISIT)
    print(f"  {'✅' if ok else '❌'} Task visit web")
    await sleep()

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

async def main():
    accounts = load_accounts()
    if not accounts:
        print("[!] Tidak ada akun yang berhasil di-load")
        sys.exit(1)

    selected = select_accounts(accounts)
    print(f"[*] Akan menjalankan {len(selected)} akun")

    for n, (i, acc) in enumerate(selected):
        await run_account(i, acc)
        if n < len(selected) - 1:
            t = random.uniform(10, 20)
            print(f"\n⏳ Jeda antar akun {t:.0f}s...")
            await asyncio.sleep(t)

    print(f"\n[*] Selesai!")

if __name__ == "__main__":
    asyncio.run(main())
