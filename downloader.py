import re
import os
import sys
import time
import random
import string
import yt_dlp
import logging
import requests
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urlencode

logger = logging.getLogger("douyin_translator")

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

def download_douyin_video_via_api(url: str, output_dir: str) -> str:
    """
    Tải video trực tiếp qua Douyin Web API (giống VIDU):
    - aBogus (ưu tiên) hoặc XBogus fallback
    - msToken thật từ mssdk hoặc fake
    - Cookie được sanitize
    - Retry 3 lần với delay tăng dần
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

    XBogus = get_xbogus_signer()
    ABogus, FingerprintGen = get_abogus_signer()
    if not XBogus and not ABogus:
        logger.warning("Không có bộ ký số (XBogus/aBogus). Bỏ qua tải API.")
        return None

    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    ms_token = _ensure_ms_token(cookies)
    logger.info(f"msToken: {ms_token[:20]}... (len={len(ms_token)})")

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

        # Ưu tiên aBogus, fallback XBogus (giống VIDU)
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
                    logger.warning(f"API detail (aid={aid}) empty 200 (anti-bot). Retrying...")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delays[min(attempt, len(retry_delays) - 1)])
                    continue

                data = response.json()
                aweme_detail = data.get("aweme_detail")
                if aweme_detail:
                    logger.info(f"SUCCESS with aid={aid} ({sign_method})!")
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

def download_douyin_video(url: str, output_dir: str = "workspace/downloads") -> str:
    """
    Downloads a Douyin video in the highest resolution.
    First tries API direct download, then yt-dlp, finally Qt WebEngine.
    """
    # 1. Thử tải trực tiếp bằng API
    logger.info("Đang thử phương thức tải trực tiếp qua Douyin API...")
    try:
        video_path = download_douyin_video_via_api(url, output_dir)
        if video_path and os.path.exists(video_path):
            return video_path
    except Exception as api_err:
        logger.warning(f"Lỗi tải trực tiếp API: {api_err}. Chuyển sang yt-dlp...")
        
    logger.info("Tải API trực tiếp không thành công hoặc không thể thực hiện. Đang chuyển sang cơ chế dự phòng yt-dlp...")
    
    clean_url = clean_and_rewrite_douyin_url(url)
    logger.info(f"Initiating download for: {clean_url}")
    
    os.makedirs(output_dir, exist_ok=True)
    
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',  # Highest quality
        'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': False,
        'no_warnings': False,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    
    # Option 1: Check for manual cookies.txt in project root
    cookie_file = "cookies.txt"
    if os.path.exists(cookie_file):
        # Copy to temp file so yt-dlp doesn't overwrite/clean our persistent cookies
        import shutil
        os.makedirs("workspace", exist_ok=True)
        temp_cookie_file = os.path.abspath("workspace/temp_cookies.txt")
        shutil.copy2(cookie_file, temp_cookie_file)
        ydl_opts['cookiefile'] = temp_cookie_file
        logger.info(f"Cookies override detected: using temp copy {temp_cookie_file}")
    else:
        # Option 2: Attempt browser cookies decryption (Chrome first, then Edge)
        logger.info("Checking for local browser cookies...")
        try:
            logger.info("Attempting Chrome cookies database...")
            chrome_opts = dict(ydl_opts)
            chrome_opts['cookiesfrombrowser'] = ('chrome',)
            with yt_dlp.YoutubeDL(chrome_opts) as ydl:
                info = ydl.extract_info(clean_url, download=True)
                return _process_download_info(ydl, info, output_dir)
        except Exception as chrome_err:
            logger.warning(f"Chrome cookies copy/decryption failed: {chrome_err}. Trying Edge...")
            try:
                edge_opts = dict(ydl_opts)
                edge_opts['cookiesfrombrowser'] = ('edge',)
                with yt_dlp.YoutubeDL(edge_opts) as ydl:
                    info = ydl.extract_info(clean_url, download=True)
                    return _process_download_info(ydl, info, output_dir)
            except Exception as edge_err:
                logger.warning(f"Edge cookies copy/decryption failed: {edge_err}. Attempting download without cookies...")
                
    # Fallback Option 3: Download without cookies or using cookies.txt if it was set
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(clean_url, download=True)
            return _process_download_info(ydl, info, output_dir)
        except Exception as e:
            error_str = str(e)
            logger.error(f"yt-dlp extraction failed: {error_str}")
            
            if "Fresh cookies" in error_str or "403" in error_str or "Sign" in error_str:
                # 4. Thử phương pháp cuối cùng: Qt WebEngine (trình duyệt thật)
                logger.info("yt-dlp yêu cầu cookie mới. Đang thử phương pháp WebEngine (trình duyệt thật)...")
                try:
                    from douyin_web_downloader import download_via_webengine
                    video_path = download_via_webengine(clean_url, output_dir)
                    if video_path and os.path.exists(video_path):
                        logger.info(f"WebEngine tải video thành công: {video_path}")
                        return video_path
                except Exception as web_err:
                    logger.error(f"WebEngine download failed: {web_err}")
                
                raise Exception(
                    "Douyin yêu cầu xác thực Cookie. Vui lòng thực hiện theo một trong các cách sau:\n\n"
                    "CÁCH 1 (TỰ ĐỘNG - KHUYÊN DÙNG):\n"
                    "1. Nhấn nút 'Đăng nhập Douyin' ở góc trên bên phải của giao diện Web.\n"
                    "2. Quét mã QR đăng nhập Douyin trên cửa sổ bật lên, hệ thống sẽ tự động lưu cookie.\n\n"
                    "CÁCH 2 (THỦ CÔNG):\n"
                    "1. Cài đặt tiện ích mở rộng 'Get cookies.txt LOCALLY' trên trình duyệt.\n"
                    "2. Truy cập douyin.com, xuất cookies và lưu thành tệp 'cookies.txt' trong thư mục dự án."
                )
            raise e

