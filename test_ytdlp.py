import os
import sys
sys.path.insert(0, r'C:\Users\CMD\Desktop\tai douin')
os.chdir(r'C:\Users\CMD\Desktop\tai douin')

import yt_dlp

url = "https://www.douyin.com/video/7642382445270109449"

ydl_opts = {
    'format': 'bestvideo+bestaudio/best',
    'outtmpl': 'test_ytdlp_%(id)s.%(ext)s',
    'merge_output_format': 'mp4',
    'noplaylist': True,
    'quiet': False,
    'no_warnings': False,
    'cookiefile': 'cookies.txt',
}

print("Testing yt-dlp with cookies.txt...")
try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        print(f"SUCCESS: {info.get('title', 'N/A')}")
        print(f"Duration: {info.get('duration', 'N/A')}s")
        print(f"Formats: {len(info.get('formats', []))}")
except Exception as e:
    print(f"FAILED: {e}")
