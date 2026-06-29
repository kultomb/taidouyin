import os, sys

# Simulate yt-dlp cookie loading
from http.cookiejar import MozillaCookieJar

cookie_file = r'C:\Users\CMD\Desktop\tai douin\cookies.txt'
jar = MozillaCookieJar()
jar.load(cookie_file, ignore_discard=True, ignore_expires=True)

print(f"Total cookies loaded: {len(jar)}")

# Check for s_v_web_id
cookies_for_douyin = []
for cookie in jar:
    if 'douyin.com' in cookie.domain:
        cookies_for_douyin.append(cookie)
        if cookie.name == 's_v_web_id':
            print(f"\nFound s_v_web_id: domain={cookie.domain}, path={cookie.path}, value={cookie.value[:50]}...")

print(f"\nCookies for douyin.com domains: {len(cookies_for_douyin)}")

# Check domain matching
from urllib.parse import urlparse
host = urlparse('https://www.douyin.com/').hostname  # 'www.douyin.com'
print(f"\nHostname for matching: {host}")

# Test _find method (what yt-dlp's _get_cookies uses)
matching = []
for cookie in jar:
    if cookie.domain in (host, f'.{host}') or host.endswith(cookie.domain.lstrip('.')):
        matching.append(cookie)

print(f"Matching cookies: {len(matching)}")
for c in matching:
    print(f"  {c.name}: domain={c.domain}")

# Test if s_v_web_id matches
sv = [c for c in matching if c.name == 's_v_web_id']
if sv:
    print(f"\ns_v_web_id found in matching cookies!")
else:
    print(f"\ns_v_web_id NOT found in matching cookies!")
    # Debug: show all s_v_web_id cookies
    all_sv = [c for c in jar if c.name == 's_v_web_id']
    print(f"All s_v_web_id in jar: {[(c.domain, c.path) for c in all_sv]}")
