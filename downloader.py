import re
import os
import sys
import time
import random
import string
import logging
import requests
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urlencode

logger = logging.getLogger("douyin_translator")

# Lazy import: yt-dlp chỉ import khi cần (không crash nếu thiếu)
_yt_dlp = None

def _get_yt_dlp():
    global _yt_dlp
    if _yt_dlp is None:
        import yt_dlp
        _yt_dlp = yt_dlp
    return _yt_dlp

def extract_url(text: str) -> str:
    """Extracts the first HTTP/HTTPS URL from a string."""
    match = re.search(r'(https?://[^\s]+)', text)
    if match:
        url = match.group(1)
        return url
    return text.strip()

def clean_and_rewrite_douyin_url(url: str) -> str:
    """
    Cleans raw text and rewrites non-standard Douyin URLs (like jingxuan with modal_id)
    to the standard video path format that yt-dlp expects.
    """
    clean_url = extract_url(url)
    
    try:
        if "douyin.com" in clean_url:
            parsed = urlparse(clean_url)
            query_params = parse_qs(parsed.query)
            
            # Rewrite /jingxuan?modal_id=xxx -> /video/xxx
            if 'modal_id' in query_params:
                video_id = query_params['modal_id'][0]
                rewritten_url = f"https://www.douyin.com/video/{video_id}"
                logger.info(f"Detected query modal_id. Rewrote URL: {clean_url} -> {rewritten_url}")
                return rewritten_url
    except Exception as e:
        logger.warning(f"Error parsing or rewriting URL: {e}")
        
    return clean_url

def load_cookies_txt(filepath="cookies.txt"):
    cookies = {}
    if not os.path.exists(filepath):
        return cookies
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('\t')
                if len(parts) >= 7:
                    domain, flag, path, secure, expiration, name, value = parts[:7]
                    # Bỏ qua cookie có tên rỗng (gây lỗi parse cho yt-dlp)
                    if not name or not name.strip():
                        continue
                    cookies[name] = value
        logger.info(f"Successfully loaded {len(cookies)} cookies from cookies.txt")
    except Exception as e:
        logger.warning(f"Failed to read cookies.txt: {e}")
    return cookies

def resolve_short_url(url, cookies=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.douyin.com/",
    }
    try:
        session = requests.Session()
        session.headers.update(headers)
        if cookies:
            session.cookies.update(cookies)
        response = session.get(url, allow_redirects=True, timeout=10)
        logger.info(f"Resolved short URL: {url} -> {response.url}")
        return response.url
    except Exception as e:
        logger.error(f"Error resolving short URL {url}: {e}")
        return url

def extract_aweme_id(url):
    match = re.search(r"/video/(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"modal_id=(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"/(?:note|gallery|slides)/(\d+)", url)
    if match:
        return match.group(1)
    return None

def get_xbogus_signer():
    try:
        from utils.xbogus import XBogus
        return XBogus
    except Exception as e:
        logger.warning(f"Could not import XBogus: {e}")
        return None

def get_abogus_signer():
    """Trả về (ABogus class, BrowserFingerprintGenerator class) hoặc (None, None)."""
    try:
        from utils.abogus import ABogus, BrowserFingerprintGenerator
        return ABogus, BrowserFingerprintGenerator
    except Exception as e:
        logger.debug(f"aBogus not available: {e}")
        return None, None

def get_ms_token_manager():
    """Trả về MsTokenManager instance để sinh msToken thật."""
    try:
        from utils.ms_token_manager import MsTokenManager
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
        return MsTokenManager(user_agent=ua)
    except Exception as e:
        logger.debug(f"MsTokenManager not available: {e}")
        return None

def _gen_fake_ms_token() -> str:
    """Tạo msToken giả 184 ký tự (giống VIDU)."""
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(182)) + "=="

def _ensure_ms_token(cookies: dict) -> str:
    """Lấy msToken: ưu tiên từ cookies, sau đó thử real từ mssdk, cuối cùng fake."""
    token = (cookies or {}).get("msToken", "").strip()
    if token:
        return token
    mgr = get_ms_token_manager()
    if mgr:
        real_token = mgr.gen_real_ms_token()
        if real_token:
            return real_token
    return _gen_fake_ms_token()

def _sanitize_cookies(cookies: dict) -> dict:
    """Lọc cookie giống VIDU: loại bỏ tên rỗng, ký tự không hợp lệ."""
    if not cookies:
        return {}
    # RFC6265: tên cookie không được chứa các ký tự đặc biệt
    invalid_chars = set('()<>@,;:\\"/[]?={} \t\r\n')
    sanitized = {}
    for key, value in cookies.items():
        if not isinstance(key, str) or not key.strip():
            continue
        k = key.strip()
        if any(ord(c) < 33 or ord(c) > 126 or c in invalid_chars for c in k):
            continue
        sanitized[k] = str(value).strip() if value is not None else ""
    return sanitized

def _build_abogus_url(base_url: str, query: str, ua: str) -> Optional[Tuple[str, str]]:
    """Tạo URL với aBogus signature. Trả về (signed_url, new_ua) hoặc None."""
    ABogus, FingerprintGen = get_abogus_signer()
    if not ABogus or not FingerprintGen:
        return None
    try:
        browser_fp = FingerprintGen.generate_fingerprint("Chrome")
        signer = ABogus(fp=browser_fp, user_agent=ua)
        params_with_ab, _ab, new_ua, _body = signer.generate_abogus(query, "")
        return f"{base_url}?{params_with_ab}", new_ua
    except Exception as e:
        logger.debug(f"Failed to generate aBogus, fallback to XBogus: {e}")
        return None

def download_douyin_video_via_api(url: str, output_dir: str, resolution: str = "1080") -> str:
    """
    Tải video trực tiếp qua Douyin Web API (giống VIDU):
    - aBogus (ưu tiên) hoặc XBogus fallback
    - msToken luôn được sinh (thật từ mssdk hoặc fake)
    - Cookie được sanitize
    - Retry khi gặp empty 200 (anti-bot)
    """
    raw_cookies = load_cookies_txt()
    cookies = _sanitize_cookies(raw_cookies)

    clean_url = clean_and_rewrite_douyin_url(url)

    if "v.douyin.com" in clean_url or "v.iesdouyin.com" in clean_url or "iesdouyin.com" in clean_url:
        long_url = resolve_short_url(clean_url, cookies)
    else:
        long_url = clean_url

    aweme_id = extract_aweme_id(long_url)
    if not aweme_id:
        logger.warning(f"Không thể trích xuất aweme_id từ URL: {long_url}")
        return None

    ABogus, FingerprintGen = get_abogus_signer()
    XBogus = get_xbogus_signer() if not ABogus else None  # chỉ fallback nếu không có aBogus

    if not XBogus and not ABogus:
        logger.warning("Không có bộ ký số (XBogus/aBogus). Bỏ qua tải API.")
        return None

    # Luôn sinh msToken (VIDU-style: ưu tiên thật, fallback fake)
    ms_token = _ensure_ms_token(cookies)
    logger.info(f"msToken: {ms_token[:20]}... (len={len(ms_token)})")

    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"

    aids = ["6383", "1128"]
    aweme_detail = None
    retry_delays = [1, 2, 5]
    max_retries = 3

    for aid in aids:
        params = {
            "device_platform": "webapp",
            "aid": aid,
            "channel": "channel_pc_web",
            "update_version_code": "170400",
            "pc_client_type": "1",
            "pc_libra_divert": "Windows",
            "version_code": "290100",
            "version_name": "29.1.0",
            "cookie_enabled": "true",
            "screen_width": "1536",
            "screen_height": "864",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "139.0.0.0",
            "browser_online": "true",
            "engine_name": "Blink",
            "engine_version": "139.0.0.0",
            "os_name": "Windows",
            "os_version": "10",
            "cpu_core_num": "16",
            "device_memory": "8",
            "platform": "PC",
            "downlink": "10",
            "effective_type": "4g",
            "round_trip_time": "200",
            "support_h265": "1",
            "support_dash": "1",
            "uifid": "",
            "aweme_id": aweme_id,
            "msToken": ms_token,
        }

        query = urlencode(params)
        base_url = "https://www.douyin.com/aweme/v1/web/aweme/detail/"

        # Ưu tiên aBogus, fallback XBogus
        ab_result = _build_abogus_url(base_url, query, ua) if ABogus else None
        if ab_result:
            signed_url, new_ua = ab_result
            sign_method = "aBogus"
        else:
            signer = XBogus(ua)
            signed_url, x_bogus, new_ua = signer.build(f"{base_url}?{query}")
            sign_method = "XBogus"

        headers = {
            "User-Agent": new_ua,
            "Referer": "https://www.douyin.com/?recommend=1",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        for attempt in range(max_retries):
            try:
                logger.info(f"Querying detail API with aid={aid} ({sign_method}, attempt {attempt+1}/{max_retries})...")
                response = requests.get(signed_url, headers=headers, cookies=cookies, timeout=10)
                if response.status_code != 200:
                    logger.warning(f"API detail (aid={aid}) HTTP {response.status_code}")
                    break

                if len(response.text) == 0:
                    # Empty 200 = Anti-bot. Retry with delay (VIDU-style)
                    logger.warning(f"API detail (aid={aid}) empty 200 (anti-bot). Retrying in {retry_delays[min(attempt, len(retry_delays)-1)]}s...")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delays[min(attempt, len(retry_delays) - 1)])
                    continue

                data = response.json()
                aweme_detail = data.get("aweme_detail")
                if aweme_detail:
                    logger.info(f"SUCCESS with aid={aid} ({sign_method})! Response={len(response.text)} bytes")
                    break
                else:
                    sc = data.get("status_code", "?")
                    sm = data.get("status_msg", "?")
                    logger.warning(f"No aweme_detail (aid={aid}): status_code={sc}, msg={sm}")
                    break
            except Exception as e:
                logger.warning(f"API error aid={aid} attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delays[min(attempt, len(retry_delays) - 1)])
                continue
            break

        if aweme_detail:
            break

    if not aweme_detail:
        logger.error("Tất cả các thử nghiệm detail API đều thất bại.")
        return None

    video = aweme_detail.get("video", {})
    bit_rates = video.get("bit_rate", [])
    play_addr = None
    if bit_rates:
        try:
            target_height = 1080 if resolution == "1080" else (720 if resolution == "720" else 99999)
            filtered_rates = []
            for item in bit_rates:
                h = item.get("height") or item.get("video_extra", {}).get("height")
                if h and isinstance(h, (int, float)):
                    if h <= target_height:
                        filtered_rates.append(item)
                else:
                    filtered_rates.append(item)
            
            if filtered_rates:
                filtered_rates.sort(key=lambda x: int(x.get("bit_rate", 0)), reverse=True)
                play_addr = filtered_rates[0].get("play_addr")
            else:
                bit_rates.sort(key=lambda x: int(x.get("bit_rate", 0)), reverse=True)
                play_addr = bit_rates[0].get("play_addr")
        except Exception:
            pass

    if not play_addr:
        play_addr = video.get("play_addr") or video.get("download_addr")

    if not play_addr or not play_addr.get("url_list"):
        logger.warning("Không tìm thấy URL luồng video nào trong phản hồi chi tiết.")
        return None

    url_candidates = [c for c in play_addr["url_list"] if c]
    url_candidates.sort(key=lambda u: 0 if "watermark=0" in u else 1)
    selected_url = url_candidates[0]

    parsed = urlparse(selected_url)
    dl_headers = {
        "Referer": "https://www.douyin.com/",
        "Origin": "https://www.douyin.com",
        "Accept": "*/*",
        "User-Agent": ua
    }

    if parsed.netloc.endswith("douyin.com") and "X-Bogus=" not in selected_url:
        selected_url, x_bogus, dl_ua = signer.build(selected_url)
        dl_headers["User-Agent"] = dl_ua

    try:
        os.makedirs(output_dir, exist_ok=True)
        dest_file = os.path.join(output_dir, f"{aweme_id}.mp4")

        logger.info(f"Đang tải video trực tiếp từ CDN URL: {selected_url}")
        r = requests.get(selected_url, headers=dl_headers, stream=True, timeout=30)
        if r.status_code == 200:
            with open(dest_file, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
            logger.info("Tải video bằng API trực tiếp thành công!")
            return os.path.abspath(dest_file)
        else:
            logger.warning(f"Tải video trực tiếp thất bại với mã lỗi HTTP {r.status_code}")
            return None

    except Exception as e:
        logger.error(f"Lỗi trong quá trình tải API trực tiếp: {e}")
        return None

def _process_download_info(ydl, info: dict, output_dir: str) -> str:
    """Helper to locate the absolute path of the downloaded video file."""
    filename = ydl.prepare_filename(info)
    base, ext = os.path.splitext(filename)
    possible_mp4 = base + ".mp4"
    
    if os.path.exists(possible_mp4):
        logger.info(f"Video downloaded successfully: {possible_mp4}")
        return os.path.abspath(possible_mp4)
    elif os.path.exists(filename):
        logger.info(f"Video downloaded successfully: {filename}")
        return os.path.abspath(filename)
        
    # Search directory as fallback
    video_id = info.get('id')
    if video_id:
        for f in os.listdir(output_dir):
            if f.startswith(video_id) and f.endswith('.mp4'):
                resolved_path = os.path.join(output_dir, f)
                logger.info(f"Video located by ID: {resolved_path}")
                return os.path.abspath(resolved_path)
                
    return os.path.abspath(filename)

def download_douyin_video(url: str, output_dir: str = "output/downloads", resolution: str = "1080") -> str:
    """
    Downloads a video in the requested resolution.
    First tries API direct download, then yt-dlp, finally Qt WebEngine.
    """
    import yt_dlp
    # 1. Thử tải trực tiếp bằng API
    logger.info("Đang thử phương thức tải trực tiếp qua Douyin API...")
    try:
        video_path = download_douyin_video_via_api(url, output_dir, resolution=resolution)
        if video_path and os.path.exists(video_path):
            return video_path
    except Exception as api_err:
        logger.warning(f"Lỗi tải trực tiếp API: {api_err}. Chuyển sang yt-dlp...")
        
    logger.info("Tải API trực tiếp không thành công hoặc không thể thực hiện. Đang chuyển sang cơ chế dự phòng yt-dlp...")
    
    clean_url = clean_and_rewrite_douyin_url(url)
    logger.info(f"Initiating download for: {clean_url}")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Ánh xạ độ phân giải sang format tương ứng của yt-dlp
    if resolution == "1080":
        fmt = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best'
    elif resolution == "720":
        fmt = 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'
    elif resolution == "best":
        fmt = 'bestvideo+bestaudio/best'
    else:
        fmt = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    if "bilibili.com" in clean_url:
        headers['Referer'] = 'https://www.bilibili.com/'
    elif "douyin.com" in clean_url:
        headers['Referer'] = 'https://www.douyin.com/'

    ydl_opts = {
        'format': fmt,
        'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': False,
        'no_warnings': False,
        'concurrent_fragment_downloads': 8,  # Tải đa luồng 8 phân đoạn song song
        'http_headers': headers
    }
    
    # Thử danh sách các phương án lấy cookie theo thứ tự ưu tiên:
    # 1. Sử dụng cookies.txt nếu có
    # 2. Trích xuất từ trình duyệt (chrome, edge, firefox, opera)
    # 3. Chạy không có cookie

    cookie_file = "cookies.txt"
    if os.path.exists(cookie_file):
        try:
            import tempfile, shutil
            temp_cookie_file = os.path.join(tempfile.gettempdir(), "taidouyin_cookies.txt")
            shutil.copy2(cookie_file, temp_cookie_file)
            cookie_opts = dict(ydl_opts)
            cookie_opts['cookiefile'] = temp_cookie_file
            logger.info(f"Đang thử tải với cookies.txt thủ công...")
            with yt_dlp.YoutubeDL(cookie_opts) as ydl:
                info = ydl.extract_info(clean_url, download=True)
                return _process_download_info(ydl, info, output_dir)
        except Exception as e:
            logger.warning(f"Tải bằng cookies.txt thất bại: {e}. Đang chuyển sang thử cookie trình duyệt...")

    # Duyệt qua các trình duyệt khả dụng
    browsers = ['chrome', 'edge', 'firefox', 'opera']
    for browser in browsers:
        try:
            logger.info(f"Đang thử trích xuất cookie từ trình duyệt: {browser}...")
            browser_opts = dict(ydl_opts)
            browser_opts['cookiesfrombrowser'] = (browser,)
            with yt_dlp.YoutubeDL(browser_opts) as ydl:
                info = ydl.extract_info(clean_url, download=True)
                return _process_download_info(ydl, info, output_dir)
        except Exception as b_err:
            logger.warning(f"Trích xuất cookie từ {browser} thất bại: {b_err}")

    # Fallback cuối cùng: Chạy không dùng cookie
    logger.info("Thử tải trực tiếp không sử dụng cookie...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(clean_url, download=True)
            return _process_download_info(ydl, info, output_dir)
        except Exception as e:
            error_str = str(e)
            logger.error(f"yt-dlp extraction failed: {error_str}")
            
            if "Fresh cookies" in error_str or "403" in error_str or "Sign" in error_str or "412" in error_str:
                # 4. Thử phương pháp cuối cùng: Qt WebEngine (trình duyệt thật)
                logger.info("Yêu cầu cookie mới hoặc gặp lỗi 412. Đang thử phương pháp WebEngine...")
                try:
                    from douyin_web_downloader import download_via_webengine
                    video_path = download_via_webengine(clean_url, output_dir)
                    if video_path and os.path.exists(video_path):
                        logger.info(f"WebEngine tải video thành công: {video_path}")
                        return video_path
                except Exception as web_err:
                    logger.error(f"WebEngine download failed: {web_err}")
                
                raise Exception(
                    "Video yêu cầu xác thực Cookie hoặc chặn truy cập (HTTP 412).\n"
                    "Vui lòng xử lý theo một trong các cách sau:\n\n"
                    "CÁCH 1 (TỰ ĐỘNG - KHUYÊN DÙNG):\n"
                    "1. Đăng nhập tài khoản Bilibili/Douyin trên trình duyệt Chrome, Edge hoặc Firefox của bạn.\n"
                    "2. Đảm bảo trình duyệt đã tải thành công video ở chế độ đăng nhập.\n\n"
                    "CÁCH 2 (THỦ CÔNG - KHI LỖI TRÌNH DUYỆT BỊ KHÓA FILE COOKIE):\n"
                    "1. Cài đặt tiện ích mở rộng 'Get cookies.txt LOCALLY' trên trình duyệt.\n"
                    "2. Truy cập trang web (douyin.com hoặc bilibili.com), xuất cookies ra file txt.\n"
                    "3. Lưu hoặc gộp nội dung vào tệp 'cookies.txt' đặt trong thư mục gốc dự án."
                )
            raise e

def get_video_info(url: str) -> dict:
    """
    Extracts available formats for the given video URL (Bilibili, Douyin, YouTube, etc.)
    and detects the maximum available height/resolution.
    Returns format options to display on the frontend.
    """
    import yt_dlp
    clean_url = clean_and_rewrite_douyin_url(url)
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }
    cookie_file = "cookies.txt"
    if os.path.exists(cookie_file):
        ydl_opts['cookiefile'] = cookie_file
    else:
        try:
            ydl_opts['cookiesfrombrowser'] = ('chrome',)
        except Exception:
            pass

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            formats = info.get("formats", [])
            max_height = 0
            for f in formats:
                h = f.get("height")
                if h and isinstance(h, int):
                    if h > max_height:
                        max_height = h
            
            if max_height <= 0:
                max_height = 1080

            logger.info(f"Video '{info.get('title')}' max height detected: {max_height}p")
            
            resolutions = []
            if max_height >= 2160:
                resolutions.append({"value": "best", "label": "4K (Chất lượng gốc)"})
                resolutions.append({"value": "1080", "label": "1080p"})
                resolutions.append({"value": "720", "label": "720p"})
            elif max_height >= 1440:
                resolutions.append({"value": "best", "label": "2K (Chất lượng gốc)"})
                resolutions.append({"value": "1080", "label": "1080p"})
                resolutions.append({"value": "720", "label": "720p"})
            elif max_height >= 1080:
                resolutions.append({"value": "1080", "label": "1080p (Chất lượng tốt nhất)"})
                resolutions.append({"value": "720", "label": "720p"})
            else:
                resolutions.append({"value": "720", "label": "720p (Chất lượng tốt nhất)"})
                
            return {
                "status": "success",
                "title": info.get("title", "Video không tiêu đề"),
                "max_height": max_height,
                "resolutions": resolutions
            }
    except Exception as e:
        logger.error(f"Error extracting video info for {url}: {e}")
        return {
            "status": "error",
            "title": "Không lấy được thông tin video",
            "max_height": 1080,
            "resolutions": [
                {"value": "1080", "label": "1080p (Mặc định)"},
                {"value": "720", "label": "720p"},
                {"value": "best", "label": "Cao nhất (Không giới hạn)"}
            ]
        }

