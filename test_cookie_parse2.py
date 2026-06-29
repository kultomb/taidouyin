import json, os, sys, time, logging
sys.path.insert(0, r'C:\Users\CMD\Desktop\tai douin')
os.chdir(r'C:\Users\CMD\Desktop\tai douin')
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test")

from http.cookiejar import MozillaCookieJar

# Simulate what yt-dlp's _get_cookies does
jar = MozillaCookieJar()
jar.load('cookies.txt', ignore_discard=True, ignore_expires=True)

# yt-dlp's _get_cookies method: https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/common.py
# It returns a dict of cookie name -> value for a given URL
from yt_dlp.extractor.common import InfoExtractor
ie = InfoExtractor()

# Check what _get_cookies returns for douyin.com
from urllib.parse import urlparse
host = urlparse('https://www.douyin.com/')
cookies_dict = ie._get_cookies('https://www.douyin.com/')
print(f"_get_cookies for douyin.com: {len(cookies_dict)} cookies")
print(f"s_v_web_id in dict: {'s_v_web_id' in cookies_dict}")

# If not found, try to understand why
if 's_v_web_id' not in cookies_dict:
    print("s_v_web_id NOT found! Checking cookie jar...")
    for cookie in jar:
        if cookie.name == 's_v_web_id':
            print(f"Cookie in jar: domain={cookie.domain}, path={cookie.path}, domain_specified={cookie.domain_specified}, domain_initial_dot={cookie.domain_initial_dot}")
    
    # Check how yt-dlp's _get_cookies matches
    # It uses http.cookiejar.DefaultCookiePolicy
    from http.cookiejar import DefaultCookiePolicy, Cookie
    policy = DefaultCookiePolicy()
    
    # The request is to https://www.douyin.com/aweme/v1/web/aweme/detail/
    request = type('Request', (), {
        'get_full_url': lambda: 'https://www.douyin.com/aweme/v1/web/aweme/detail/',
        'get_host': lambda: 'www.douyin.com',
        'get_type': lambda: 'https',
        'is_unverifiable': lambda: False,
        'has_header': lambda x: False,
        'get_header': lambda x, default=None: default,
        'header_items': lambda: [],
        'unverifiable': False,
        'origin_req_host': None,
    })()
    
    # Check if the cookie would be returned
    for cookie in jar:
        if cookie.name == 's_v_web_id':
            result = policy.set_ok(cookie, request)
            print(f"set_ok for s_v_web_id: {result}")

# Also test with the actual yt-dlp cookie file option
print("\n--- Testing yt-dlp with cookiefile ---")
import yt_dlp
ydl_opts = {
    'format': 'best',
    'quiet': False,
    'outtmpl': 'test_video.%(ext)s',
    'cookiefile': 'cookies.txt',
    'noplaylist': True,
}

try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info('https://www.douyin.com/video/7642382445270109449', download=False)
        print(f"SUCCESS: {info.get('title', 'N/A')}")
except Exception as e:
    print(f"ERROR: {e}")
