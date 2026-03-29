# Nexus Downloader — Build Guide

## Quick Start (Windows)

1. Make sure **Python 3.10 or newer** is installed and on your PATH.
2. Open this folder in File Explorer.
3. Double-click **`build.bat`**.
4. The finished EXE will appear at **`dist\NexusDownloader.exe`**.

---

## Manual Build (any OS)

```bash
# Install dependencies
pip install pyinstaller PySide6 yt-dlp requests packaging pillow

# Build
pyinstaller NexusDownloader.spec
```

Output: `dist/NexusDownloader` (or `dist/NexusDownloader.exe` on Windows)

---

## What's Included in the EXE

| File | Purpose |
|------|---------|
| `logo.png` | Animated logo shown in the header bar |
| `Icon.ico` | App icon (taskbar, Alt-Tab, file icon) |
| `themes.py` | Dark / Light theme definitions |
| `widgets/` | All custom UI widget modules |

---

## Logo Changes (v8)

- **Header bar**: The old `▶` emoji placeholder is replaced with the real
  Nexus Downloader logo image (`logo.png`).
- The logo animates with a **smooth sine-wave breathe** (scales 95 % → 105 %)
  and a **blue/purple radial glow** pulse behind it — same timing as the
  original animated icon.
- The new `LogoAnimatedIcon` widget is in `widgets/animated_components.py`
  and degrades gracefully (draws a gradient "N" circle) if `logo.png` is
  missing at runtime.
- `Icon.ico` has been regenerated from the logo PNG at sizes 16 → 256 px.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: No module named 'yt_dlp'` | Run `pip install yt-dlp` |
| UPX warning during build | Install [UPX](https://upx.github.io/) or set `upx=False` in the spec |
| App icon missing in taskbar | Ensure `Icon.ico` is in the same folder as `main.py` |
| Logo not showing in header | Ensure `logo.png` is in the same folder as `main.py` |
