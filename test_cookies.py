import json
import os
import sys
sys.path.insert(0, r'C:\Users\CMD\Desktop\tai douin')
os.chdir(r'C:\Users\CMD\Desktop\tai douin')

from downloader import load_cookies_txt
cookies = load_cookies_txt('cookies.txt')
print(f'Cookies loaded: {len(cookies)}')
for k, v in cookies.items():
    if len(str(v)) > 50:
        print(f'  {k}: {str(v)[:50]}...')
    else:
        print(f'  {k}: {v}')

print()
important = ['sessionid', 'sessionid_ss', 'sid_guard', 'passport_csrf_token', 'odin_tt', 'ttwid', 'msToken']
for k in important:
    status = "YES" if k in cookies else "MISSING"
    print(f'  {k}: {status}')
