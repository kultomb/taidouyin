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

class DouyinCookieWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trình Xác Thực Cookie Douyin (FastAPI SaaS)")
        self.resize(1024, 768)

        # In-memory store for captured cookies
        self.collected_cookies = {}

        # Set up UI
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Header instructions
        self.header_label = QLabel(
            "<b>HƯỚNG DẪN XÁC THỰC:</b><br/>"
            "1. Vui lòng đăng nhập tài khoản Douyin của bạn trong cửa sổ bên dưới (quét mã QR hoặc đăng nhập SMS).<br/>"
            "2. Nếu hệ thống hiển thị slide captcha (kéo hình), hãy hoàn thành captcha trên giao diện.<br/>"
            "3. Khi bạn thấy trang chủ Douyin tải xong ở trạng thái đã đăng nhập, hãy nhấn nút <b>LƯU COOKIE & ĐÓNG</b> bên dưới."
        )
        self.header_label.setStyleSheet("font-size: 13px; color: #2c3e50; margin: 5px;")
        layout.addWidget(self.header_label)

        # Web view
        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)

        # Bottom buttons panel
        bottom_panel = QWidget()
        bottom_layout = QHBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel("Đang kết nối tới Douyin...")
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

        # Set up cookie listener
        self.profile = QWebEngineProfile.defaultProfile()
        self.profile.setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        self.cookie_store = self.profile.cookieStore()
        # Clear all existing cookies first to ensure a clean login session
        self.cookie_store.deleteAllCookies()
        
        self.cookie_store.cookieAdded.connect(self.on_cookie_added)

        # Load Douyin
        self.web_view.setUrl(QUrl("https://www.douyin.com"))
        self.web_view.loadFinished.connect(self.on_load_finished)

    def on_load_finished(self, success):
        if success:
            self.status_label.setText("Đã tải xong trang Douyin. Vui lòng đăng nhập.")
        else:
            self.status_label.setText("Tải trang thất bại. Vui lòng kiểm tra lại kết nối mạng.")

    def on_cookie_added(self, cookie: QNetworkCookie):
        domain = cookie.domain()
        # Only collect douyin cookies to keep file clean
        if "douyin.com" not in domain:
            return

        name = cookie.name().data().decode("utf-8", errors="ignore")
        # Bỏ qua cookie có tên rỗng (gây lỗi parse Netscape format)
        if not name or not name.strip():
            return
        
        path = cookie.path()
        value = cookie.value().data().decode("utf-8", errors="ignore")
        secure = "TRUE" if cookie.isSecure() else "FALSE"
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"

        if cookie.isSessionCookie() or not cookie.expirationDate().isValid():
            # Set to 1 year in the future instead of 0 to prevent yt-dlp/cookielib from discarding it
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

        # Tự động lưu và đóng khi phát hiện đã đăng nhập thành công
        # sessionid hoặc sessionid_ss là dấu hiệu đăng nhập thành công
        if name in ("sessionid", "sessionid_ss") and value:
            self.status_label.setText("Đăng nhập thành công! Đang lưu cookie và tự động đóng...")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2500, lambda: self.save_cookies_and_close(auto_trigger=True))

    def save_cookies_and_close(self, auto_trigger=False):
        if not self.collected_cookies:
            if not auto_trigger:
                QMessageBox.warning(
                    self,
                    "Cảnh báo",
                    "Chưa ghi nhận được cookie nào từ Douyin. Vui lòng đợi trang web tải xong và đăng nhập thử."
                )
            return

        # Prepare cookies.txt contents in Netscape format
        lines = [
            "# Netscape HTTP Cookie File",
            "# This file is generated by get_cookies_gui.py",
            "# Do not edit manually unless you know what you are doing.",
            ""
        ]

        for cookie_data in self.collected_cookies.values():
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

        # Write to cookies.txt in the current directory
        cookie_file_path = os.path.abspath("cookies.txt")
        try:
            with open(cookie_file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            
            if not auto_trigger:
                QMessageBox.information(
                    self,
                    "Thành công",
                    f"Đã lưu thành công {len(self.collected_cookies)} cookies vào tệp:\n{cookie_file_path}\n\nBạn có thể chạy lại tiến trình dịch video ngay bây giờ."
                )
            else:
                print(f"[SUCCESS] Tự động lưu {len(self.collected_cookies)} cookies thành công!")
                names = [c['name'] for c in self.collected_cookies.values()]
                print(f"[COOKIES_LIST] {','.join(names)}")
            self.close()
        except Exception as e:
            if not auto_trigger:
                QMessageBox.critical(
                    self,
                    "Lỗi",
                    f"Không thể ghi tệp cookies.txt: {e}"
                )
            else:
                print(f"[ERROR] Không thể tự động ghi tệp cookies.txt: {e}")

def main():
    app = QApplication(sys.argv)
    window = DouyinCookieWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
