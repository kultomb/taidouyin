# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect all data, binaries, and hidden imports for external libraries
datas = []
binaries = []
hiddenimports = []

packages_to_collect = [
    'rapidocr_onnxruntime',
    'faster_whisper',
    'edge_tts',
    'google.genai',
    'google.cloud.texttospeech',
    'yt_dlp'
]

for pkg in packages_to_collect:
    tmp_datas, tmp_binaries, tmp_hiddenimports = collect_all(pkg)
    datas.extend(tmp_datas)
    binaries.extend(tmp_binaries)
    hiddenimports.extend(tmp_hiddenimports)

# Find and include ffmpeg & ffprobe binaries inside the EXE
import shutil
def find_ffmpeg_binaries():
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    
    # Check common Chocolatey path if default path check is a shim
    choco_path = r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin"
    if os.path.exists(os.path.join(choco_path, "ffmpeg.exe")):
        return os.path.join(choco_path, "ffmpeg.exe"), os.path.join(choco_path, "ffprobe.exe")
        
    return ffmpeg, ffprobe

ffmpeg_exe, ffprobe_exe = find_ffmpeg_binaries()
if ffmpeg_exe and os.path.exists(ffmpeg_exe):
    print(f"Bundling ffmpeg: {ffmpeg_exe}")
    datas.append((ffmpeg_exe, '.'))
else:
    print("WARNING: ffmpeg.exe not found! Bundled app might fail to run correctly if not installed on target system.")

if ffprobe_exe and os.path.exists(ffprobe_exe):
    print(f"Bundling ffprobe: {ffprobe_exe}")
    datas.append((ffprobe_exe, '.'))
else:
    print("WARNING: ffprobe.exe not found! Bundled app might fail to run correctly if not installed on target system.")

# Add static files folder so that HTML/JS/CSS are bundled inside the EXE
datas.append(('static', 'static'))

# Add prompts folder so Gemini translation prompts are available at runtime
if os.path.exists('prompts'):
    for f in os.listdir('prompts'):
        src = os.path.join('prompts', f)
        if os.path.isfile(src):
            datas.append((src, 'prompts'))

# Add fonts folder if it exists (for OCR / ASS subtitle rendering)
if os.path.exists('fonts'):
    for f in os.listdir('fonts'):
        src = os.path.join('fonts', f)
        if os.path.isfile(src):
            datas.append((src, 'fonts'))

# Hidden imports needed for uvicorn + fastapi in frozen EXE
hiddenimports.extend([
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'starlette',
    'starlette.routing',
    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',
])


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Check if a custom icon exists
icon_path = 'icons/app_icon.ico' if os.path.exists('icons/app_icon.ico') else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DouyinTranslator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to False to hide the black CMD command line window!
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)
