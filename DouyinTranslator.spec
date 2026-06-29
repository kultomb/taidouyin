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

# Add static files folder so that HTML/JS/CSS are bundled inside the EXE
datas.append(('static', 'static'))

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
