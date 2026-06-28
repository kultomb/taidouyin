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
print(f"Keys: {list(cookies.keys())}")

# From utils.xbogus import XBogus
sys.path.insert(0, os.path.abspath('.'))
from utils.xbogus import XBogus

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
xb = XBogus(ua)

# Test detail API
aweme_id = "7642382445270109449"
# Generate real msToken
from utils.ms_token_manager import MsTokenManager
mgr = MsTokenManager(user_agent=ua)
real_ms_token = mgr.gen_real_ms_token()
print(f"Real msToken len: {len(real_ms_token)}")

params = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "aweme_id": aweme_id,
    "msToken": real_ms_token,
}

from urllib.parse import urlencode
base = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
query = urlencode(params)
signed_url, x_bogus, new_ua = xb.build(f"{base}?{query}")

headers = {
    "User-Agent": new_ua,
    "Referer": "https://www.douyin.com/?recommend=1",
}

r = requests.get(signed_url, headers=headers, cookies=cookies, timeout=15)
print(f"Status: {r.status_code}")
print(f"Content-Type: {r.headers.get('Content-Type', '?')}")
print(f"Body len: {len(r.text)}")
if r.text:
    print(f"Body[:500]: {r.text[:500]}")
else:
    print("Body is EMPTY - anti-bot detected!")
