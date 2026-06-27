"""
Douyin Video Downloader sử dụng Qt WebEngine để tải video trực tiếp.
Phương pháp: Mở trang video trong trình duyệt Qt WebEngine (Chromium thật),
bắt URL video từ network request, sau đó tải xuống.
"""
import sys
import os
import time
import requests
import logging
from typing import Optional

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineUrlRequestInterceptor
from PyQt6.QtCore import QUrl, QTimer, pyqtSignal, QObject

logger = logging.getLogger("douyin_translator")


class VideoUrlInterceptor(QWebEngineUrlRequestInterceptor):
    """Bắt tất cả network request để tìm URL video .mp4 thật từ CDN."""

    # Các domain CDN video của Douyin
    VIDEO_CDN_PATTERNS = [
        'douyinvod.com',      # v3-web-prime.douyinvod.com
        'zjcdn.com',           # v5-dy-ov-experiment.zjcdn.com
        'bytecdn.com',         # bytecdn.cn
        'bytedance.com/video', # video CDN paths
        'ibytedtos.com',
        'douyin.com/aweme/v1/play/',  # Play API redirect
    ]

    def __init__(self):
        super().__init__()
        self.video_urls = []
        self.video_title = ""
        self._page_url = ""  # URL của trang video để loại trừ

    def set_page_url(self, url: str):
        self._page_url = url

    def interceptRequest(self, info):
        url = info.requestUrl().toString()

        # Bỏ qua URL của chính trang video
        if url == self._page_url or url.rstrip('/') == self._page_url.rstrip('/'):
            return

        # Bỏ qua static assets (douyinstatic.com)
        if 'douyinstatic.com' in url:
            return

        # Chỉ bắt URL từ CDN video hoặc có đuôi .mp4
        is_video_cdn = any(pattern in url for pattern in self.VIDEO_CDN_PATTERNS)
        is_mp4 = '.mp4' in url.lower()

        if is_video_cdn or is_mp4:
            if url not in self.video_urls:
                self.video_urls.append(url)
                logger.info(f"[WebEngine] Phát hiện URL video: {url[:150]}...")


class DouyinWebDownloader(QMainWindow):
    """Mở trang Douyin trong WebEngine, bắt video URL, tải xuống."""

    download_finished = pyqtSignal(str)  # Emits file path on success
    download_failed = pyqtSignal(str)    # Emits error message

    def __init__(self, video_url: str, output_dir: str):
        super().__init__()
        self.video_url = video_url
        self.output_dir = output_dir
        self.downloaded_path: Optional[str] = None
        self.error_msg: Optional[str] = None
        self._timeout_timer: Optional[QTimer] = None
        self._check_timer: Optional[QTimer] = None

        # Không hiển thị cửa sổ
        self.setWindowTitle("Douyin Video Downloader")
        self.resize(800, 600)

        # Thiết lập profile & interceptor
        self.profile = QWebEngineProfile.defaultProfile()
        self.profile.setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
        )

        # Load cookies từ cookies.txt nếu có
        self._load_cookies_into_profile()

        # Interceptor bắt video URL
        self.interceptor = VideoUrlInterceptor()
        self.profile.setUrlRequestInterceptor(self.interceptor)

        # Web view
        self.web_view = QWebEngineView()
        self.setCentralWidget(self.web_view)
        self.web_view.loadFinished.connect(self._on_page_loaded)

        # Timeout sau 30 giây
        self._timeout_timer = QTimer()
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

    def _load_cookies_into_profile(self):
        """Nạp cookies từ cookies.txt vào WebEngine profile."""
        cookie_file = "cookies.txt"
        if not os.path.exists(cookie_file):
            return

        cookie_store = self.profile.cookieStore()
        try:
            with open(cookie_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        from PyQt6.QtNetwork import QNetworkCookie
                        from PyQt6.QtCore import QDateTime

                        domain, flag, path, secure_str, expiration_str, name, value = parts[:7]
                        if not name or not name.strip():
                            continue

                        cookie = QNetworkCookie()
                        cookie.setDomain(domain)
                        cookie.setPath(path)
                        cookie.setName(name.encode('utf-8'))
                        cookie.setValue(value.encode('utf-8'))
                        cookie.setSecure(secure_str.upper() == "TRUE")

                        try:
                            exp = int(expiration_str)
                            if exp > 0:
                                expiry = QDateTime.fromSecsSinceEpoch(exp)
                                cookie.setExpirationDate(expiry)
                        except (ValueError, OverflowError):
                            pass

                        cookie_store.setCookie(cookie)
            logger.info(f"Đã nạp cookies vào WebEngine profile")
        except Exception as e:
            logger.warning(f"Không thể nạp cookies vào WebEngine: {e}")

    def start(self):
        """Bắt đầu quá trình tải."""
        self.interceptor.set_page_url(self.video_url)
        logger.info(f"[WebEngine] Đang mở trang video: {self.video_url}")
        self.web_view.setUrl(QUrl(self.video_url))
        self._timeout_timer.start(60000)  # 60 giây timeout
        # Định kỳ kiểm tra URL video mỗi 5 giây
        self._check_timer = QTimer()
        self._check_timer.timeout.connect(self._check_video_urls)
        self._check_timer.start(5000)

    def _check_video_urls(self):
        """Định kỳ kiểm tra xem đã có URL video thật chưa (không phải static assets)."""
        # Chỉ count URL từ CDN video thật (có /video/tos/ trong path)
        real_cdn_urls = [u for u in self.interceptor.video_urls
                         if '/video/tos/' in u or 'douyinvod.com' in u or 'zjcdn.com' in u]
        if real_cdn_urls:
            logger.info(f"[WebEngine] Đã phát hiện {len(real_cdn_urls)} CDN video URL thật, bắt đầu tải...")
            self._check_timer.stop()
            self._try_download()

    def _on_page_loaded(self, success: bool):
        """Khi trang web tải xong."""
        if not success:
            self._fail("Không thể tải trang Douyin. Kiểm tra kết nối mạng.")
            return

        logger.info("[WebEngine] Trang đã tải xong. Đang chờ video load...")

        # Thử inject JavaScript để lấy video URL từ DOM
        js_code = """
        (function() {
            var urls = [];
            var videos = document.querySelectorAll('video');
            for (var i = 0; i < videos.length; i++) {
                var src = videos[i].src || videos[i].getAttribute('src');
                if (src) urls.push(src);
                var sources = videos[i].querySelectorAll('source');
                for (var j = 0; j < sources.length; j++) {
                    if (sources[j].src) urls.push(sources[j].src);
                }
            }
            return JSON.stringify(urls);
        })();
        """
        self.web_view.page().runJavaScript(js_code, self._on_js_result)

        # Tăng tần suất check sau khi page load: mỗi 2 giây
        if self._check_timer:
            self._check_timer.setInterval(2000)

        # Thử tải sau 15 giây (đủ thời gian cho video player khởi tạo)
        QTimer.singleShot(15000, self._try_download)

    def _on_js_result(self, result):
        """Xử lý kết quả từ JavaScript."""
        if result:
            try:
                import json
                urls = json.loads(result)
                for url in urls:
                    if url and url not in self.interceptor.video_urls:
                        self.interceptor.video_urls.append(url)
                        logger.info(f"[WebEngine JS] Phát hiện URL video: {url[:120]}...")
            except Exception:
                pass

    def _try_download(self):
        """Thử tải video từ URL đã bắt được."""
        all_urls = self.interceptor.video_urls

        if not all_urls:
            logger.warning("[WebEngine] Không phát hiện URL video nào. Đợi thêm...")
            QTimer.singleShot(5000, self._try_download_final)
            return

        # Ưu tiên URL từ CDN video (có /video/tos/ trong path)
        cdn_videos = [u for u in all_urls if '/video/tos/' in u]
        # Sau đó là URL .mp4
        mp4_urls = [u for u in all_urls if '.mp4' in u.lower()]
        # Sau đó là URL từ play API
        play_urls = [u for u in all_urls if '/aweme/v1/play/' in u]
        # Còn lại
        other_urls = [u for u in all_urls if u not in cdn_videos and u not in mp4_urls and u not in play_urls]

        candidate_urls = cdn_videos + mp4_urls + play_urls + other_urls

        logger.info(f"[WebEngine] Tìm thấy {len(candidate_urls)} URL video: "
                     f"{len(cdn_videos)} CDN, {len(mp4_urls)} MP4, {len(play_urls)} Play API")
        self._download_video(candidate_urls[0])

    def _try_download_final(self):
        """Lần thử cuối cùng sau khi đợi thêm."""
        all_urls = self.interceptor.video_urls
        if not all_urls:
            self._fail("Không phát hiện được URL video. Có thể video đã bị xóa hoặc ở chế độ riêng tư.")
            return
        self._download_video(all_urls[0])

    def _download_video(self, video_url: str):
        """Tải video từ URL đã tìm thấy."""
        logger.info(f"[WebEngine] Đang tải video từ: {video_url[:150]}...")

        os.makedirs(self.output_dir, exist_ok=True)

        # Trích xuất tên file từ URL hoặc dùng timestamp
        filename = f"douyin_video_{int(time.time())}.mp4"
        dest_file = os.path.join(self.output_dir, filename)

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
                "Referer": "https://www.douyin.com/",
                "Origin": "https://www.douyin.com",
            }
            r = requests.get(video_url, headers=headers, stream=True, timeout=60, allow_redirects=True)
            if r.status_code == 200:
                content_type = r.headers.get('Content-Type', '')
                content_length = r.headers.get('Content-Length')

                # Kiểm tra Content-Type là video (đôi khi CDN không trả về đúng)
                if 'text/html' in content_type:
                    logger.warning(f"[WebEngine] URL trả về HTML thay vì video, bỏ qua...")
                    remaining = [u for u in self.interceptor.video_urls if u != video_url]
                    if remaining:
                        logger.info(f"[WebEngine] Thử URL dự phòng...")
                        self._download_video(remaining[0])
                        return
                    self._fail("Tất cả URL đều trả về HTML thay vì video.")
                    return

                with open(dest_file, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                file_size = os.path.getsize(dest_file)
                if file_size > 1024:  # Lớn hơn 1KB mới coi là video hợp lệ
                    logger.info(f"[WebEngine] Tải video thành công! Size: {file_size / 1024 / 1024:.1f}MB")
                    self.downloaded_path = os.path.abspath(dest_file)
                    self._finish()
                    return
                else:
                    os.remove(dest_file)
                    logger.warning(f"[WebEngine] File quá nhỏ ({file_size} bytes), không phải video.")

            logger.warning(f"[WebEngine] Tải video thất bại, HTTP {r.status_code}")
            # Thử URL tiếp theo nếu có
            remaining = [u for u in self.interceptor.video_urls if u != video_url]
            if remaining:
                logger.info(f"[WebEngine] Thử URL dự phòng...")
                self._download_video(remaining[0])
                return

            self._fail(f"Tải video thất bại (HTTP {r.status_code})")
        except Exception as e:
            logger.error(f"[WebEngine] Lỗi tải video: {e}")
            # Thử URL tiếp theo
            remaining = [u for u in self.interceptor.video_urls if u != video_url]
            if remaining:
                logger.info(f"[WebEngine] Thử URL dự phòng sau lỗi...")
                self._download_video(remaining[0])
                return
            self._fail(f"Lỗi tải video: {str(e)}")

    def _on_timeout(self):
        """Xử lý khi timeout."""
        if not self.downloaded_path:
            self._fail("Quá thời gian chờ tải video (45 giây).")

    def _finish(self):
        """Hoàn thành thành công."""
        self._timeout_timer.stop()
        if self._check_timer:
            self._check_timer.stop()
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().quit()
        self.close()

    def _fail(self, msg: str):
        """Thất bại."""
        self.error_msg = msg
        self._timeout_timer.stop()
        if self._check_timer:
            self._check_timer.stop()
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().quit()
        self.close()


def download_via_webengine(video_url: str, output_dir: str) -> Optional[str]:
    """
    Tải video Douyin bằng Qt WebEngine.
    Trả về đường dẫn file đã tải, hoặc None nếu thất bại.
    """
    # Qt cần QApplication đã tồn tại
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    downloader = DouyinWebDownloader(video_url, output_dir)
    downloader.start()
    downloader.show()  # Hiển thị để WebEngine hoạt động

    # Chạy event loop cho đến khi cửa sổ đóng
    app.exec()

    if downloader.downloaded_path:
        return downloader.downloaded_path
    elif downloader.error_msg:
        raise Exception(f"WebEngine download failed: {downloader.error_msg}")
    else:
        return None


# ========== TEST ==========
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.douyin.com/video/7642382445270109449"
    test_dir = sys.argv[2] if len(sys.argv) > 2 else "output/test_webengine"

    print(f"Testing WebEngine download for: {test_url}")
    try:
        path = download_via_webengine(test_url, test_dir)
        print(f"SUCCESS: {path}")
    except Exception as e:
        print(f"FAILED: {e}")
