@echo off
title Douyin Video Translator Pro
echo ==============================================================
echo       KHOI DONG DOUYIN VIDEO TRANSLATOR SAAS
echo ==============================================================
echo.
echo [1/2] Dang mo trinh duyet web tai http://localhost:8001...
:: Wait 1 second before starting browser to sync with backend startup
timeout /t 2 /nobreak > nul
start http://localhost:8001

echo [2/2] Dang khoi chay FastAPI Backend Server (Auto-Reload ON)...
echo.
echo ==============================================================
echo   DA BAT AUTO-RELOAD: Khi ban sua code, server tu dong load lai
echo   KHONG CAN chay lai run.bat. Chi can luu file la duoc!
echo   Muon dung: nhan Ctrl+C
echo ==============================================================
echo.
python main.py

echo May chu da dung.
pause
