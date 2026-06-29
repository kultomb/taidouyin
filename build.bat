@echo off
title Douyin Video Translator - Build EXE
setlocal EnableExtensions
cd /d "%~dp0"

echo ==============================================================
echo       DOUYIN VIDEO TRANSLATOR - BUILD EXE (PORTABLE)
echo ==============================================================
echo.
echo Workspace: %CD%
echo.

:: Check for Python virtual environment
if exist ".venv\Scripts\activate.bat" (
    echo [1/4] Activating Virtual Environment...
    call .venv\Scripts\activate.bat
) else (
    echo [1/4] Virtual environment not found, using global python...
)

echo.
echo [2/4] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 goto :fail

:: Ensure pyinstaller is installed
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing pyinstaller...
    pip install pyinstaller
    if errorlevel 1 goto :fail
)

echo.
echo [3/4] Building PyInstaller executable (No Console window)...
pyinstaller DouyinTranslator.spec --noconfirm --clean
if errorlevel 1 goto :fail

echo.
echo [4/4] Saving to dist\releases...
if not exist "dist\releases" mkdir "dist\releases"
if not exist "dist\DouyinTranslator.exe" (
    echo ERROR: Cannot find dist\DouyinTranslator.exe
    goto :fail
)
copy /Y "dist\DouyinTranslator.exe" "dist\releases\DouyinTranslator.exe" >nul

echo.
echo ==============================================================
echo  BUILD SUCCESSFUL!
echo  Executable saved to: %CD%\dist\releases\DouyinTranslator.exe
echo.
echo  * Run DouyinTranslator.exe directly.
echo  * It will run silently in the background (no black CMD window).
echo  * It will automatically open http://localhost:8001 in your browser.
echo ==============================================================
pause
exit /b 0

:fail
echo.
echo ==============================================================
echo  BUILD FAILED! Please check the errors above.
echo ==============================================================
pause
exit /b 1
