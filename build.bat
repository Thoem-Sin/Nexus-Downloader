@echo off
:: ============================================================
::  Nexus Downloader — EXE Build Script
::  Double-click this file (or run in CMD) from the project folder
:: ============================================================

echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ and add to PATH.
    pause & exit /b 1
)

echo [2/4] Installing / upgrading dependencies...
pip install --quiet --upgrade pyinstaller PySide6 yt-dlp requests packaging pillow

echo [3/4] Cleaning previous build...
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist

echo [4/4] Building EXE...
pyinstaller NexusDownloader.spec

if errorlevel 1 (
    echo.
    echo BUILD FAILED. Check errors above.
    pause & exit /b 1
)

echo.
echo ============================================================
echo  SUCCESS!  Your EXE is at:
echo  dist\NexusDownloader.exe
echo ============================================================
pause
