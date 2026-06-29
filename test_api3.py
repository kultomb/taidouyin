import json, os, sys, time, logging, requests
sys.path.insert(0, r'C:\Users\CMD\Desktop\tai douin')
os.chdir(r'C:\Users\CMD\Desktop\tai douin')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test")

from downloader import load_cookies_txt, _sanitize_cookies, _ensure_ms_token, get_xbogus_signer, get_abogus_signer
from urllib.parse import urlencode
from utils.ms_token_manager import MsTokenManager

cookies_raw = load_cookies_txt('cookies.txt')
cookies = _sanitize_cookies(cookies_raw)

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"

# Use session (giống VIDU)
session = requests.Session()
session.headers.update({
    "User-Agent": ua,
    "Referer": "https://www.douyin.com/",
    "Accept": "application/json, text/plain, */*",
})
session.cookies.update(cookies)

# Visit homepage first
try:
    r_home = session.get("https://www.douyin.com/?recommend=1", timeout=10)
    logger.info(f"Homepage: status={r_home.status_code}, url_length={len(r_home.text)}")
except Exception as e:
    logger.warning(f"Homepage failed: {e}")

# Generate real msToken
mgr = MsTokenManager(user_agent=ua)
ms_token = mgr.gen_real_ms_token()
logger.info(f"Real msToken: len={len(ms_token)}")

video_id = "7642382445270109449"
aid = "6383"

params = {
    "aid": aid,
    "aweme_id": video_id,
    "device_platform": "webapp",
    "channel": "channel_pc_web",
    "pc_client_type": "1",
    "version_code": "290100",
    "version_name": "29.1.0",
    "cookie_enabled": "true",
    "screen_width": "1920",
    "screen_height": "1080",
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Chrome",
    "browser_version": "139.0.0.0",
    "browser_online": "true",
    "os_name": "Windows",
    "os_version": "10",
    "platform": "PC",
    "msToken": ms_token,
}

query = urlencode(params)
base_url = "https://www.douyin.com/aweme/v1/web/aweme/detail/"

# Test with XBogus
XSigner = get_xbogus_signer()
if XSigner:
    signer = XSigner(ua)
    signed_url, x_bogus, new_ua = signer.build(f"{base_url}?{query}")
    
    headers = {
        "User-Agent": new_ua,
        "Referer": "https://www.douyin.com/?recommend=1",
        "Accept": "application/json, text/plain, */*",
    }
    
    logger.info(f"Calling API with XBogus + real msToken + session cookies...")
    r = session.get(signed_url, headers=headers, timeout=15)
    logger.info(f"Status: {r.status_code}, len: {len(r.text)}, content-type: {r.headers.get('content-type','?')}")
    
    if r.text:
        try:
            data = r.json()
            ad = data.get("aweme_detail")
            if ad:
                logger.info(f"SUCCESS! aweme_detail keys: {list(ad.keys())[:20]}")
                logger.info(f"desc: {ad.get('desc', 'N/A')[:50]}")
            else:
                logger.info(f"JSON but no aweme_detail: {json.dumps(data, ensure_ascii=False)[:300]}")
        except:
            logger.info(f"Non-JSON response: {r.text[:300]}")
    else:
        logger.info("Empty response body")

# Also try with aid=1128
logger.info("---")
aid2 = "1128"
params2 = dict(params)
params2["aid"] = aid2
query2 = urlencode(params2)
signed_url2, x_bogus2, new_ua2 = signer.build(f"{base_url}?{query2}")
headers2 = {
    "User-Agent": new_ua2,
    "Referer": "https://www.douyin.com/?recommend=1",
    "Accept": "application/json, text/plain, */*",
}
r2 = session.get(signed_url2, headers=headers2, timeout=15)
logger.info(f"aid={aid2}: Status: {r2.status_code}, len: {len(r2.text)}")
if r2.text:
    try:
        data2 = r2.json()
        ad2 = data2.get("aweme_detail")
        if ad2:
            logger.info(f"SUCCESS! desc: {ad2.get('desc', 'N/A')[:50]}")
        else:
            logger.info(f"JSON: {json.dumps(data2, ensure_ascii=False)[:300]}")
    except:
        logger.info(f"Non-JSON: {r2.text[:200]}")
