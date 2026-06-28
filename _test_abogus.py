import requests, json, os, sys

with open('cookies.txt', 'r') as f:
    raw = f.read().strip()

cookies = {}
for line in raw.split('\n'):
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    parts = line.split('\t')
    if len(parts) >= 7:
        name = parts[5].strip()
        value = parts[6].strip()
        if name:
            cookies[name] = value

print(f"Loaded {len(cookies)} cookies")

sys.path.insert(0, os.path.abspath('.'))
from utils.xbogus import XBogus
from utils.abogus import ABogus, BrowserFingerprintGenerator
from utils.ms_token_manager import MsTokenManager
from urllib.parse import urlencode

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"

mgr = MsTokenManager(user_agent=ua)
real_ms_token = mgr.gen_real_ms_token()
print(f"msToken len: {len(real_ms_token)}")

aweme_id = "7642382445270109449"
params = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "aweme_id": aweme_id,
    "msToken": real_ms_token,
}

query = urlencode(params)
base = "https://www.douyin.com/aweme/v1/web/aweme/detail/"

# Test aBogus
print(f"\n=== aBogus ===")
fp = BrowserFingerprintGenerator.generate_fingerprint("Chrome")
signer = ABogus(fp=fp, user_agent=ua)
params_with_ab, a_bogus, new_ua_ab, _ = signer.generate_abogus(query, "")
ab_url = f"{base}?{params_with_ab}"
print(f"aBogus: {a_bogus[:40]}...")
r2 = requests.get(ab_url, headers={"User-Agent": new_ua_ab, "Referer": "https://www.douyin.com/?recommend=1"}, cookies=cookies, timeout=15)
print(f"Status: {r2.status_code}, Body len: {len(r2.text)}")
if r2.text:
    try:
        data = r2.json()
        aweme = data.get("aweme_detail")
        if aweme:
            print(f"SUCCESS! aweme_detail keys: {list(aweme.keys())[:8]}")
        else:
            print(f"No aweme_detail: {json.dumps(data, ensure_ascii=False)[:200]}")
    except:
        print(f"Raw[:300]: {r2.text[:300]}")
else:
    print("Body EMPTY - still blocked")
