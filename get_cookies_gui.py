import sys
import os
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QMessageBox
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile
from PyQt6.QtCore import QUrl
from PyQt6.QtNetwork import QNetworkCookie

def load_existing_cookies(filepath):
    """Đọc và phân tích file cookies.txt cũ nếu có để chuẩn bị gộp."""
    cookies = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        domain, sub, path, secure, exp, name, val = parts[:7]
                        cookies[(domain, path, name)] = {
                            'domain': domain,
                            'include_subdomains': sub,
                            'path': path,
                            'secure': secure,
                            'expiration': exp,
                            'name': name,
                            'value': val
                        }
        except Exception as e:
            print(f"Lỗi đọc file cookies cũ: {e}")
    return cookies

class MultiPlatformCookieWindow(QMainWindow):
    def __init__(self, platform="douyin"):
        super().__init__()
        self.platform = platform.lower()
        
        # Thiết lập cấu hình tùy theo nền tảng
        if self.platform == "bilibili":
            self.setWindowTitle("Trình Xác Thực Cookie Bilibili (FastAPI SaaS)")
            self.filter_domain = "bilibili.com"
            self.target_url = "https://www.bilibili.com"
            self.success_cookies = ("SESSDATA",)
            self.platform_name = "Bilibili"
            instructions = (
                "<b>HƯỚNG DẪN XÁC THỰC BILIBILI:</b><br/>"
                "1. Vui lòng đăng nhập tài khoản Bilibili của bạn ở cửa sổ bên dưới (Quét mã QR hoặc SMS/Mật khẩu).<br/>"
                "2. Hoàn thành kéo captcha (nếu có) trên màn hình.<br/>"
                "3. Khi đã đăng nhập xong và hiển thị Avatar của bạn, bấm nút <b>LƯU COOKIE & ĐÓNG</b> bên dưới."
            )
        elif self.platform == "youtube":
            self.setWindowTitle("Trình Xác Thực Cookie YouTube (FastAPI SaaS)")
            self.filter_domain = "youtube.com"
            self.target_url = "https://www.youtube.com"
            self.success_cookies = ("SID", "LOGIN_INFO")
            self.platform_name = "YouTube"
            instructions = (
                "<b>HƯỚNG DẪN XÁC THỰC YOUTUBE:</b><br/>"
                "1. Vui lòng đăng nhập tài khoản Google / YouTube của bạn ở cửa sổ bên dưới.<br/>"
                "2. Thực hiện các bước xác minh 2 lớp (nếu có) do Google yêu cầu.<br/>"
                "3. Khi đã đăng nhập xong và hiển thị trang chủ YouTube ở trạng thái đăng nhập, bấm nút <b>LƯU COOKIE & ĐÓNG</b> bên dưới."
            )
        else:  # Mặc định là douyin
            self.setWindowTitle("Trình Xác Thực Cookie Douyin (FastAPI SaaS)")
            self.filter_domain = "douyin.com"
            self.target_url = "https://www.douyin.com"
            self.success_cookies = ("sessionid", "sessionid_ss")
            self.platform_name = "Douyin"
            instructions = (
                "<b>HƯỚNG DẪN XÁC THỰC DOUYIN:</b><br/>"
                "1. Vui lòng đăng nhập tài khoản Douyin của bạn ở cửa sổ bên dưới (Quét mã QR hoặc SMS).<br/>"
                "2. Hoàn thành kéo captcha (nếu có) trên màn hình.<br/>"
                "3. Khi đã đăng nhập xong và hiển thị trang chủ Douyin của bạn, bấm nút <b>LƯU COOKIE & ĐÓNG</b> bên dưới."
            )

        self.resize(1024, 768)
        self.collected_cookies = {}

        # Giao diện chính
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Nhãn hướng dẫn
        self.header_label = QLabel(instructions)
        self.header_label.setStyleSheet("font-size: 13px; color: #2c3e50; margin: 5px;")
        layout.addWidget(self.header_label)

        # Trình duyệt nhúng
        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)

        # Hàng nút bấm ở dưới
        bottom_panel = QWidget()
        bottom_layout = QHBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel(f"Đang kết nối tới {self.platform_name}...")
        self.status_label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        bottom_layout.addWidget(self.status_label)

        bottom_layout.addStretch()

        self.save_btn = QPushButton("LƯU COOKIE & ĐÓNG")
        self.save_btn.setStyleSheet(
            "background-color: #2ecc71; color: white; font-weight: bold; "
            "padding: 8px 16px; border: none; border-radius: 4px; font-size: 13px;"
        )
        self.save_btn.clicked.connect(self.save_cookies_and_close)
        bottom_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Hủy")
        self.cancel_btn.setStyleSheet(
            "background-color: #e74c3c; color: white; "
            "padding: 8px 16px; border: none; border-radius: 4px; font-size: 13px;"
        )
        self.cancel_btn.clicked.connect(self.close)
        bottom_layout.addWidget(self.cancel_btn)

        layout.addWidget(bottom_panel)

        # Lắng nghe cookie phát sinh
        self.profile = QWebEngineProfile.defaultProfile()
        self.profile.setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        self.cookie_store = self.profile.cookieStore()
        self.cookie_store.cookieAdded.connect(self.on_cookie_added)

        # Tải trang
        self.web_view.setUrl(QUrl(self.target_url))
        self.web_view.loadFinished.connect(self.on_load_finished)

    def on_load_finished(self, success):
        if success:
            self.status_label.setText(f"Đã tải xong trang {self.platform_name}. Vui lòng đăng nhập.")
        else:
            self.status_label.setText("Tải trang thất bại. Vui lòng kiểm tra kết nối mạng.")

    def on_cookie_added(self, cookie: QNetworkCookie):
        domain = cookie.domain()
        
        # Lọc tên miền tương ứng
        if self.platform == "youtube":
            # Cho phép cả google.com và youtube.com vì đăng nhập YouTube phụ thuộc Google
            if "youtube.com" not in domain and "google.com" not in domain:
                return
        else:
            if self.filter_domain not in domain:
                return

        name = cookie.name().data().decode("utf-8", errors="ignore")
        if not name or not name.strip():
            return
        
        path = cookie.path()
        value = cookie.value().data().decode("utf-8", errors="ignore")
        secure = "TRUE" if cookie.isSecure() else "FALSE"
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"

        if cookie.isSessionCookie() or not cookie.expirationDate().isValid():
            expiration = str(int(time.time() + 365 * 24 * 3600))
        else:
            expiration = str(int(cookie.expirationDate().toSecsSinceEpoch()))

        self.collected_cookies[(domain, path, name)] = {
            'domain': domain,
            'include_subdomains': include_subdomains,
            'path': path,
            'secure': secure,
            'expiration': expiration,
            'name': name,
            'value': value
        }

        # Tự động lưu và đóng nếu phát hiện cookie đăng nhập thành công
        if name in self.success_cookies and value:
            self.status_label.setText("Đăng nhập thành công! Đang lưu và tự động đóng...")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2500, lambda: self.save_cookies_and_close(auto_trigger=True))

    def save_cookies_and_close(self, auto_trigger=False):
        if not self.collected_cookies:
            if not auto_trigger:
                QMessageBox.warning(
                    self,
                    "Cảnh báo",
                    f"Chưa ghi nhận được cookie nào từ {self.platform_name}. Vui lòng đăng nhập trước khi lưu."
                )
            return

        cookie_file_path = os.path.abspath("cookies.txt")
        
        # ── Thuật toán Gộp Cookie thông minh (Smart Merge) ──
        existing_cookies = load_existing_cookies(cookie_file_path)
        
        # Chèn đè hoặc chèn mới cookie thu thập được vào danh sách hiện tại
        for key, cookie_data in self.collected_cookies.items():
            existing_cookies[key] = cookie_data

        # Tạo nội dung Netscape cookie format mới từ danh sách đã gộp
        lines = [
            "# Netscape HTTP Cookie File",
            "# This file is generated by get_cookies_gui.py (Merged)",
            "# Do not edit manually unless you know what you are doing.",
            ""
        ]

        for cookie_data in existing_cookies.values():
            line = (
                f"{cookie_data['domain']}\t"
                f"{cookie_data['include_subdomains']}\t"
                f"{cookie_data['path']}\t"
                f"{cookie_data['secure']}\t"
                f"{cookie_data['expiration']}\t"
                f"{cookie_data['name']}\t"
                f"{cookie_data['value']}"
            )
            lines.append(line)

        try:
            with open(cookie_file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            
            if not auto_trigger:
                QMessageBox.information(
                    self,
                    "Thành công",
                    f"Đã lưu và gộp thành công {len(self.collected_cookies)} cookies {self.platform_name} vào cookies.txt!"
                )
            else:
                print(f"[SUCCESS] Tự động gộp {len(self.collected_cookies)} cookies thành công!")
            self.close()
        except Exception as e:
            if not auto_trigger:
                QMessageBox.critical(
                    self,
                    "Lỗi",
                    f"Không thể ghi tệp cookies.txt: {e}"
                )
            else:
                print(f"[ERROR] Không thể ghi tệp cookies.txt: {e}")

def main():
    app = QApplication(sys.argv)
    
    # Nhận tham số dòng lệnh để xác định platform
    platform = "douyin"
    if len(sys.argv) > 1:
        platform = sys.argv[1]
        
    window = MultiPlatformCookieWindow(platform=platform)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
