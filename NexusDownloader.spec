# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Nexus Downloader
# Run:  pyinstaller NexusDownloader.spec

from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import sys, os

block_cipher = None

# ── Collect PySide6 / yt-dlp hidden imports ──────────────────────────────────
hidden = (
    collect_submodules('PySide6') +
    collect_submodules('yt_dlp') +
    ['packaging', 'packaging.version', 'requests']
)

# ── Data files bundled inside the EXE ────────────────────────────────────────
#    Format: (source_path,  destination_folder_inside_bundle)
datas = [
    ('logo.png',   '.'),
    ('Icon.ico',   '.'),
    ('themes.py',  '.'),
    ('widgets',    'widgets'),
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NexusDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # smaller EXE (install UPX if available)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # no black console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='Icon.ico',    # taskbar + file icon
    version_file=None,
)
