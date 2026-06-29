import json, os, sys, time, random, string, requests, logging
sys.path.insert(0, r'C:\Users\CMD\Desktop\tai douin')
os.chdir(r'C:\Users\CMD\Desktop\tai douin')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test")

from downloader import load_cookies_txt, _ensure_ms_token, get_xbogus_signer

cookies = load_cookies_txt('cookies.txt')

# Get real msToken
import time as _time
from utils.ms_token_manager import MsTokenManager
ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
mgr = MsTokenManager(user_agent=ua)
ms_token = mgr.gen_real_ms_token()
logger.info(f"Real msToken: {ms_token} (len={len(ms_token)})")

from urllib.parse import urlencode

video_id = "7642382445270109449"
params = {
    "aweme_id": video_id,
    "aid": "6383",
    "device_platform": "web",
    "browser_name": "chrome",
    "browser_version": "139.0.0.0",
    "os_name": "windows",
    "region": "vn",
    "tz_name": "Asia/Ho_Chi_Minh",
    "cookie_enabled": "true",
    "screen_width": "1920",
    "screen_height": "1080",
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_online": "true",
}

if ms_token:
    params["msToken"] = ms_token

query = urlencode(params)
base_url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/"

# Try with XBogus
XSigner = get_xbogus_signer()
if XSigner:
    signer = XSigner(ua)
    signed_url, x_bogus, new_ua = signer.build(f"{base_url}?{query}")
    headers = {
        "User-Agent": new_ua,
        "Referer": "https://www.douyin.com/",
        "Accept": "application/json",
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
    }
    logger.info(f"Trying XBogus URL: {signed_url[:100]}...")
    r = requests.get(signed_url, headers=headers, timeout=15)
    logger.info(f"XBogus response: status={r.status_code}, len={len(r.text)}, content-type={r.headers.get('content-type','?')}")
    logger.info(f"Response body: {r.text[:500]}")

# Also try without signature
logger.info("---")
headers2 = {
    "User-Agent": ua,
    "Referer": "https://www.douyin.com/",
    "Accept": "application/json",
    "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
}
r2 = requests.get(f"{base_url}?{query}", headers=headers2, timeout=15)
logger.info(f"No-sign response: status={r2.status_code}, len={len(r2.text)}, content-type={r2.headers.get('content-type','?')}")
logger.info(f"Response body: {r2.text[:500]}")
