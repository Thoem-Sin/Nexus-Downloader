"""Channel/Profile scraper worker - fetches video list from a channel or profile URL"""

import re
import json
import sys
import subprocess

_HIDE = {}
if sys.platform == "win32":
    _HIDE["creationflags"] = subprocess.CREATE_NO_WINDOW
from typing import List, Dict, Optional
from PySide6.QtCore import QThread, Signal


def is_channel_or_profile_url(url: str) -> bool:
    """Return True if the URL looks like a channel, profile, or playlist page."""
    patterns = [
        # YouTube
        r'youtube\.com/channel/',
        r'youtube\.com/c/',
        r'youtube\.com/user/',
        r'youtube\.com/@[\w\-\.]+/?$',             # profile root  e.g. /@MrBeast
        r'youtube\.com/@[\w\-\.]+/videos',          # /videos tab
        r'youtube\.com/@[\w\-\.]+/shorts',          # /shorts tab
        r'youtube\.com/@[\w\-\.]+/streams',         # /streams (live) tab
        r'youtube\.com/@[\w\-\.]+/live',            # /live tab
        r'youtube\.com/@[\w\-\.]+/playlists',       # /playlists tab
        r'youtube\.com/@[\w\-\.]+/releases',        # /releases tab
        r'youtube\.com/@[\w\-\.]+/podcasts',        # /podcasts tab
        r'youtube\.com/playlist\?list=',
        # Vimeo
        r'vimeo\.com/channels/',
        r'vimeo\.com/showcase/',
        r'vimeo\.com/album/',
        r'vimeo\.com/[\w]+/?$',               # vimeo user profile
        # Twitch
        r'twitch\.tv/[\w]+/videos',
        r'twitch\.tv/collections/',
        # Twitter / X
        r'(twitter|x)\.com/[\w]+/?$',
        r'(twitter|x)\.com/i/lists/',
        # TikTok
        r'tiktok\.com/@[\w\.]+/?$',
        # Dailymotion
        r'dailymotion\.com/[\w]+/?$',
        r'dailymotion\.com/playlist/',
        # Bilibili
        r'bilibili\.com/bangumi/',
        r'space\.bilibili\.com/\d+',
    ]
    for p in patterns:
        if re.search(p, url, re.IGNORECASE):
            return True
    return False


def extract_profile_name(url: str) -> Optional[str]:
    """Extract profile/channel name from a URL for use as subfolder name."""
    url_lower = url.lower()
    
    # YouTube @handle (e.g., /@MrBeast)
    match = re.search(r'youtube\.com/@([\w\-]+)', url_lower)
    if match:
        return match.group(1)
    
    # YouTube channel ID (e.g., /channel/UC...)
    match = re.search(r'youtube\.com/channel/([\w\-]+)', url_lower)
    if match:
        return match.group(1)
    
    # YouTube /c/ (custom URL)
    match = re.search(r'youtube\.com/c/([\w\-]+)', url_lower)
    if match:
        return match.group(1)
    
    # YouTube /user/
    match = re.search(r'youtube\.com/user/([\w\-]+)', url_lower)
    if match:
        return match.group(1)
    
    # TikTok @handle
    match = re.search(r'tiktok\.com/@([\w\.]+)', url_lower)
    if match:
        return match.group(1)
    
    # Twitter/X @handle
    match = re.search(r'(twitter|x)\.com/([\w]+)/?$', url_lower)
    if match:
        return match.group(2)
    
    # Twitch channel
    match = re.search(r'twitch\.tv/([\w]+)', url_lower)
    if match:
        return match.group(1)
    
    # Dailymotion user
    match = re.search(r'dailymotion\.com/([\w]+)/?$', url_lower)
    if match:
        return match.group(1)
    
    # Vimeo user
    match = re.search(r'vimeo\.com/([\w]+)/?$', url_lower)
    if match:
        return match.group(1)
    
    return None


class ChannelScraperWorker(QThread):
    """Scrapes video list from a channel / profile URL using yt-dlp --flat-playlist."""

    # Emitted gradually as items are found
    video_found = Signal(dict)           # one video info dict at a time
    # Emitted once at the end
    scrape_finished = Signal(list, str)  # (video_list, error_message)
    progress_update = Signal(str)        # status text

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self.progress_update.emit("Connecting to channel…")
            videos = self._scrape()
            if self._cancelled:
                self.scrape_finished.emit([], "Cancelled")
                return
            if not videos:
                self.scrape_finished.emit([], "No videos found. The channel may be private or empty.")
                return
            self.scrape_finished.emit(videos, "")
        except Exception as e:
            self.scrape_finished.emit([], str(e))

    def _scrape(self) -> List[Dict]:
        """Use yt-dlp --flat-playlist to list videos without downloading."""
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--dump-json",
            "--no-warnings",
            # No --playlist-end: scrape the entire channel/playlist
            self.url,
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                **_HIDE,
            )
        except FileNotFoundError:
            # yt-dlp not installed – return demo data
            return self._demo_videos()

        videos = []
        count = 0
        for line in proc.stdout:
            if self._cancelled:
                proc.terminate()
                return videos
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Skip playlist-level entries (they have no direct URL)
            if data.get("_type") == "playlist":
                title = data.get("title") or data.get("channel") or "Channel"
                self.progress_update.emit(f"Scanning '{title}'…")
                continue

            url = data.get("url") or data.get("webpage_url") or data.get("id")
            if not url:
                continue

            # Build a full URL if only the video ID was returned
            if not url.startswith("http"):
                extractor = data.get("ie_key", "").lower()
                if "youtube" in extractor or not extractor:
                    url = f"https://www.youtube.com/watch?v={url}"
                elif "vimeo" in extractor:
                    url = f"https://vimeo.com/{url}"
                else:
                    url = f"https://www.youtube.com/watch?v={url}"

            duration_secs = data.get("duration") or 0
            video = {
                "url": url,
                "title": data.get("title") or data.get("fulltitle") or "Untitled",
                "uploader": (
                    data.get("uploader")
                    or data.get("channel")
                    or data.get("playlist_uploader")
                    or "Unknown"
                ),
                "duration": self._fmt_duration(duration_secs),
                "thumbnail": data.get("thumbnail") or data.get("thumbnails", [{}])[0].get("url", "") if data.get("thumbnails") else data.get("thumbnail", ""),
                "view_count": data.get("view_count") or 0,
                "id": data.get("id") or "",
            }
            videos.append(video)
            count += 1
            self.video_found.emit(video)
            # Show milestone hint every 100 so the user knows it's still scanning
            if count % 100 == 0:
                self.progress_update.emit(f"Found {count} videos… (still scanning)")
            else:
                self.progress_update.emit(f"Found {count} video{'s' if count != 1 else ''}…")

        proc.wait()
        return videos

    @staticmethod
    def _fmt_duration(secs) -> str:
        try:
            secs = int(secs)
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            if h:
                return f"{h}:{m:02d}:{s:02d}"
            return f"{m}:{s:02d}"
        except Exception:
            return ""

    @staticmethod
    def _demo_videos() -> List[Dict]:
        """Return fake videos when yt-dlp is not installed (demo / dev mode)."""
        return [
            {"url": f"https://www.youtube.com/watch?v=demo{i}",
             "title": f"Demo Video {i}: Amazing Content You'll Love",
             "uploader": "Demo Channel",
             "duration": f"{i % 10 + 1}:{(i * 13 % 60):02d}",
             "thumbnail": "",
             "view_count": i * 1000,
             "id": f"demo{i}"}
            for i in range(1, 9)
        ]
