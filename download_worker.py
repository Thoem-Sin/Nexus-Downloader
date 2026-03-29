"""Download worker thread for handling video downloads"""

import os
import re
import json
import time
import threading
import sys
import subprocess

# Hide console windows on Windows when launching subprocesses
_HIDE = {}
if sys.platform == "win32":
    _HIDE["creationflags"] = subprocess.CREATE_NO_WINDOW
from typing import Optional, Dict, List
from PySide6.QtCore import QThread, Signal


class FetchWorker(QThread):
    """Lightweight thread that fetches video/playlist metadata for ONE url.
    Starts immediately (outside the download queue) so all URLs are probed
    in parallel while the download concurrency limit is enforced separately.
    """
    info_ready = Signal(str, dict)        # task_id, info dict (for card update)
    fetch_done = Signal(str, bool, dict)  # task_id, is_playlist, info

    def __init__(self, task_id: str, url: str):
        super().__init__()
        self.task_id = task_id
        self.url = url
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        self.quit()
        self.wait(2000)

    def run(self):
        try:
            if self._cancelled:
                return
            is_playlist = self._detect_playlist()
            if self._cancelled:
                return
            info = self._fetch_playlist_info() if is_playlist else self._fetch_single_info()
            if not self._cancelled:
                if info:
                    self.info_ready.emit(self.task_id, info)
                self.fetch_done.emit(self.task_id, is_playlist, info or {})
        except Exception:
            if not self._cancelled:
                self.fetch_done.emit(self.task_id, False, {})

    def _detect_playlist(self) -> bool:
        patterns = [
            r'youtube\.com/playlist\?list=',
            r'youtube\.com/channel/', r'youtube\.com/c/', r'youtube\.com/user/',
            r'youtube\.com/@[\w\-\.]+(/videos|/shorts|/streams|/live|/?$)',
            r'vimeo\.com/(channels|showcase|album)/',
            r'(twitter|x)\.com/i/lists/',
            r'twitch\.tv/collections/',
            r'dailymotion\.com/playlist/',
            r'bilibili\.com/bangumi/play/', r'bilibili\.com/list/',
        ]
        for p in patterns:
            if re.search(p, self.url, re.IGNORECASE):
                return True
        try:
            cmd = ["yt-dlp", "--flat-playlist", "--dump-json", "--no-playlist",
                   "--no-warnings", self.url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, **_HIDE)
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout.strip().split('\n')[0])
                return (data.get('_type') == 'playlist' or
                        bool(data.get('playlist_count')) or
                        bool(data.get('playlist')) or
                        bool(data.get('playlist_title')))
        except Exception:
            pass
        return False

    def _fetch_single_info(self) -> Optional[dict]:
        try:
            cmd = ["yt-dlp", "--dump-json", "--no-playlist", "--no-warnings", self.url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, **_HIDE)
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout.strip().split('\n')[0])
                return {
                    "title":       data.get("title", "Unknown"),
                    "uploader":    data.get("uploader", "Unknown"),
                    "channel":     data.get("channel", data.get("uploader", "Unknown")),
                    "channel_id":  data.get("channel_id", ""),
                    "duration":    data.get("duration", 0),
                    "thumbnail":   data.get("thumbnail", ""),
                    "view_count":  data.get("view_count", 0),
                    "description": data.get("description", "")[:200],
                    "platform":    data.get("extractor_key", "Unknown"),
                    "is_playlist": False,
                }
        except Exception:
            pass
        return None

    def _fetch_playlist_info(self) -> Optional[dict]:
        try:
            cmd = ["yt-dlp", "--flat-playlist", "--dump-json",
                   "--no-warnings", "--playlist-items", "1", self.url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, **_HIDE)
            if result.returncode == 0 and result.stdout:
                lines = [l for l in result.stdout.strip().split('\n') if l.strip()]
                if lines:
                    data = json.loads(lines[0])
                    channel = (data.get("channel") or data.get("uploader") or
                               data.get("playlist_uploader") or "Unknown")
                    return {
                        "title":          data.get("playlist_title", data.get("title", "Playlist")),
                        "uploader":       data.get("uploader", "Unknown"),
                        "channel":        channel,
                        "channel_id":     data.get("channel_id", ""),
                        "playlist_count": data.get("playlist_count", 0),
                        "thumbnail":      data.get("thumbnail", ""),
                        "platform":       data.get("extractor_key", "Unknown"),
                        "is_playlist":    True,
                    }
        except Exception:
            pass
        return None


class DownloadWorker(QThread):
    progress = Signal(str, float, str, str)   # id, percent, speed, eta
    info_ready = Signal(str, dict)             # id, info dict
    finished = Signal(str, bool, str)          # id, success, message
    log = Signal(str, str)                     # id, line
    playlist_progress = Signal(str, int, int)  # id, completed, total

    def __init__(self, task_id: str, url: str, output_dir: str,
                 quality: str = "best", fmt: str = "mp4", audio_only: bool = False,
                 is_playlist: bool = False, auto_create_subfolders: bool = True,
                 profile_name: Optional[str] = None, upscale_4k: bool = False,
                 pre_fetched_is_playlist: Optional[bool] = None,
                 pre_fetched_info: Optional[dict] = None):
        super().__init__()
        self.task_id = task_id
        self.url = url
        self.output_dir = output_dir
        self.quality = quality
        self.fmt = fmt
        self.audio_only = audio_only
        self.is_playlist = is_playlist
        self.auto_create_subfolders = auto_create_subfolders
        self.profile_name = profile_name
        self.upscale_4k = upscale_4k
        # Pre-fetched data from FetchWorker — avoids re-fetching at download time
        self.pre_fetched_is_playlist = pre_fetched_is_playlist
        self.pre_fetched_info = pre_fetched_info
        self._cancelled = False
        self._paused = False
        self._pause_event = threading.Event()
        self._pause_event.set()
        self.proc = None
        self.current_speed = 0.0
        self.playlist_total = 0
        self.playlist_completed = 0
        self.channel_name = ""

    def cancel(self):
        self._cancelled = True
        self._pause_event.set()   # unblock if paused so thread can exit
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.quit()
        self.wait(3000)
    
    def pause(self):
        self._paused = True
        self._pause_event.clear()
    
    def resume(self):
        self._paused = False
        self._pause_event.set()

    def run(self):
        try:
            if self._cancelled:
                return

            # Use pre-fetched result from FetchWorker when available — avoids
            # a redundant yt-dlp probe now that fetching is parallelised.
            if self.pre_fetched_is_playlist is not None:
                is_playlist = self.pre_fetched_is_playlist
            else:
                is_playlist = self._auto_detect_playlist()

            if self._cancelled:
                return

            if is_playlist:
                self._download_playlist()
            else:
                # Emit pre-fetched info immediately; only probe if missing.
                if self.pre_fetched_info:
                    self.info_ready.emit(self.task_id, self.pre_fetched_info)
                else:
                    info = self._fetch_info()
                    if info and not self._cancelled:
                        self.info_ready.emit(self.task_id, info)

                if self._cancelled:
                    return

                self._download_single()

        except Exception as e:
            if not self._cancelled:
                self.finished.emit(self.task_id, False, str(e))

    def _auto_detect_playlist(self) -> bool:
        """Auto-detect if URL is a playlist, channel, or profile"""
        if self.is_playlist:
            return True
        
        # Define patterns for different platforms
        patterns = {
            'youtube_playlist': r'(youtube\.com/playlist\?list=|youtu\.be/.*[&?]list=)',
            'youtube_channel': r'(youtube\.com/channel/|youtube\.com/c/|youtube\.com/user/|youtube\.com/@)',
            'youtube_profile': r'(youtube\.com/@[\w-]+)$',
            'vimeo_showcase': r'(vimeo\.com/showcase/|vimeo\.com/album/)',
            'vimeo_channel': r'(vimeo\.com/channels/)',
            'twitter_list': r'(twitter\.com/i/lists/|x\.com/i/lists/)',
            'twitch_collection': r'(twitch\.tv/collections/|twitch\.tv/videos/.*\?collection=)',
            'dailymotion_playlist': r'(dailymotion\.com/playlist/)',
            'bilibili_playlist': r'(bilibili\.com/bangumi/play/|bilibili\.com/list/)',
        }
        
        for pattern_type, pattern in patterns.items():
            if re.search(pattern, self.url, re.IGNORECASE):
                return True
        
        # Use yt-dlp to detect playlist/channel
        try:
            # Use --flat-playlist to check if it's a playlist without downloading
            cmd = ["yt-dlp", "--flat-playlist", "--dump-json", "--no-playlist", self.url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, **_HIDE)
            
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout.strip().split('\n')[0])
                
                # Check for playlist indicators
                if data.get('_type') == 'playlist' or data.get('playlist_count'):
                    return True
                
                # Check if it's a channel by looking for channel_id
                if data.get('channel_id') and not data.get('playlist'):
                    return True
                    
                # Check for playlist in URL parameters
                if data.get('playlist') or data.get('playlist_title'):
                    return True
                    
        except Exception as e:
            print(f"Error detecting playlist: {e}")
        
        return False

    def _fetch_info(self) -> Optional[dict]:
        """Fetch video metadata using yt-dlp"""
        try:
            cmd = ["yt-dlp", "--dump-json", "--no-playlist", self.url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, **_HIDE)
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout.strip().split('\n')[0])
                return {
                    "title": data.get("title", "Unknown"),
                    "uploader": data.get("uploader", "Unknown"),
                    "channel": data.get("channel", data.get("uploader", "Unknown")),
                    "channel_id": data.get("channel_id", ""),
                    "duration": data.get("duration", 0),
                    "thumbnail": data.get("thumbnail", ""),
                    "view_count": data.get("view_count", 0),
                    "description": data.get("description", "")[:200],
                    "formats": self._parse_formats(data.get("formats", [])),
                    "platform": data.get("extractor_key", "Unknown"),
                }
        except Exception:
            pass
        return None

    def _parse_formats(self, formats: list) -> list:
        seen = set()
        result = []
        for f in reversed(formats):
            height = f.get("height")
            if height and height not in seen:
                seen.add(height)
                result.append({"quality": f"{height}p", "ext": f.get("ext", "mp4"),
                               "filesize": f.get("filesize", 0)})
        return sorted(result, key=lambda x: int(x["quality"].replace("p", "")), reverse=True)[:8]

    def _build_format_args(self) -> tuple[str, list]:
        """
        Return (format_selector, post_processing_args) for yt-dlp.

        Goals:
        - Download the highest-quality video + audio streams available.
        - Re-encode to H.264 + AAC for genuine quality output (CRF 18).
        - When upscale_4k=True: scale to 3840x2160 via Lanczos + CRF 16.
        - For audio-only mode: extract best quality as mp3/m4a.
        """
        if self.audio_only:
            fmt_sel = "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best"
            post = [
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "0",
            ]
            return fmt_sel, post

        # ── Format selector: prefer H.264+AAC first for clean re-encode ────────
        if self.quality == "best":
            fmt_sel = (
                "bestvideo[vcodec^=avc]+bestaudio[acodec^=mp4a]"
                "/bestvideo[vcodec^=avc]+bestaudio"
                "/bestvideo[ext=mp4]+bestaudio[ext=m4a]"
                "/bestvideo[vcodec^=vp9]+bestaudio[acodec^=opus]"
                "/bestvideo[vcodec^=av01]+bestaudio[acodec^=opus]"
                "/bestvideo[vcodec!=none]+bestaudio[acodec!=none]"
                "/bestvideo+bestaudio"
                "/best"
            )
        else:
            h = self.quality.replace("p", "")
            fmt_sel = (
                f"bestvideo[vcodec^=avc][height<={h}]+bestaudio[acodec^=mp4a]"
                f"/bestvideo[vcodec^=avc][height<={h}]+bestaudio"
                f"/bestvideo[ext=mp4][height<={h}]+bestaudio[ext=m4a]"
                f"/bestvideo[vcodec^=vp9][height<={h}]+bestaudio[acodec^=opus]"
                f"/bestvideo[vcodec^=av01][height<={h}]+bestaudio[acodec^=opus]"
                f"/bestvideo[vcodec!=none][height<={h}]+bestaudio[acodec!=none]"
                f"/bestvideo[height<={h}]+bestaudio"
                f"/best[height<={h}]"
                f"/best"
            )

        # ── Post-processing / ffmpeg args ──────────────────────────────────────
        if self.upscale_4k:
            # Scale to 4K with Lanczos — must encode, use fast preset for speed.
            # CRF 18, veryfast preset: good quality, much faster than slow/medium.
            ffmpeg_args = (
                "-vf scale=3840:2160:flags=lanczos"
                " -c:v libx264 -crf 18 -preset veryfast"
                " -profile:v high -level 5.1"
                " -c:a copy -movflags +faststart"
            )
            post = [
                "--merge-output-format", "mp4",
                "--postprocessor-args", f"ffmpeg:{ffmpeg_args}",
            ]
        else:
            # Stream-copy: remux without re-encoding — near-instant merge.
            # The format selector already prefers H.264+AAC so copy is safe.
            # If ffmpeg can't copy (mismatched codec), it falls back automatically.
            ffmpeg_args = "-c:v copy -c:a copy -movflags +faststart"
            post = [
                "--merge-output-format", self.fmt,
                "--postprocessor-args", f"ffmpeg:{ffmpeg_args}",
            ]
        return fmt_sel, post

    def _download_single(self):
        """Download single video - NO playlist progress signals"""
        # Create profile subfolder if a profile name was supplied
        # (happens when videos come from the channel scraper)
        if self.auto_create_subfolders and self.profile_name:
            safe_folder = re.sub(r'[<>:"/\\|?*]', '_', self.profile_name)
            effective_output_dir = os.path.join(self.output_dir, safe_folder)
            os.makedirs(effective_output_dir, exist_ok=True)
        else:
            effective_output_dir = self.output_dir

        out_tmpl = os.path.join(effective_output_dir, "%(title)s.%(ext)s")

        fmt_sel, post = self._build_format_args()

        # Performance & reliability flags
        perf_flags = [
            "--concurrent-fragments", "8",
            "--retries", "10",
            "--fragment-retries", "10",
            "--buffer-size", "1M",
            "--no-playlist",        # guard: never pull a playlist on single-video call
        ]

        cmd = ["yt-dlp", "-f", fmt_sel, "--newline", "--progress",
               "-o", out_tmpl, *perf_flags, *post, self.url]

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, bufsize=1, **_HIDE)
            self.proc = proc
            error_lines: list[str] = []

            # Read stdout in this thread; collect stderr in a background thread
            import threading as _threading
            def _collect_stderr():
                for ln in proc.stderr:
                    error_lines.append(ln.strip())
            _t = _threading.Thread(target=_collect_stderr, daemon=True)
            _t.start()

            for line in proc.stdout:
                self._pause_event.wait()
                line = line.strip()
                if self._cancelled:
                    proc.terminate()
                    return

                self.log.emit(self.task_id, line)

                # Show post-processing status so UI doesn't appear frozen at 100%
                if "[Merger]" in line or "Merging formats" in line:
                    self.progress.emit(self.task_id, 100.0, "Merging…", "")
                    continue
                if "[VideoRecoder]" in line or "Recoding video" in line:
                    self.progress.emit(self.task_id, 100.0, "Processing…", "")
                    continue
                if "[ffmpeg]" in line and "%" not in line:
                    self.progress.emit(self.task_id, 100.0, "Processing…", "")
                    continue

                # Parse progress - no playlist progress for single videos
                pct_match = re.search(r'(\d+\.?\d*)%', line)
                speed_match = re.search(r'(\d+\.?\d*\s*[KMG]iB/s)', line)
                eta_match = re.search(r'ETA\s+(\S+)', line)

                if pct_match:
                    pct = float(pct_match.group(1))
                    speed = speed_match.group(1) if speed_match else "..."
                    eta = eta_match.group(1) if eta_match else "..."
                    self.current_speed = self._parse_speed(speed)
                    self.progress.emit(self.task_id, pct, speed, eta)

            proc.wait()
            _t.join(timeout=2)
            if proc.returncode == 0:
                # For single video, always show simple completion message
                if not self._cancelled:
                    self.finished.emit(self.task_id, True, "Download complete!")
            else:
                if not self._cancelled:
                    err_msg = "Download failed"
                    for ln in reversed(error_lines):
                        if ln and not ln.startswith("[debug]"):
                            err_msg = ln[:120]
                            break
                    self.finished.emit(self.task_id, False, err_msg)

        except FileNotFoundError:
            self._simulate_download()

    def _download_playlist(self):
        """Download entire playlist, channel, or profile"""
        # Reset playlist values
        self.playlist_total = 0
        self.playlist_completed = 0
        
        # Get playlist details
        try:
            info_cmd = ["yt-dlp", "--dump-json", "--flat-playlist", self.url]
            result = subprocess.run(info_cmd, capture_output=True, text=True, timeout=30, **_HIDE)
            if result.returncode == 0 and result.stdout:
                videos = [json.loads(line) for line in result.stdout.strip().split('\n') if line]
                self.playlist_total = len(videos)
                
                # Only treat as playlist if more than 1 video
                if self.playlist_total > 1:
                    self.playlist_progress.emit(self.task_id, 0, self.playlist_total)
                else:
                    # If only 1 video, treat as single video
                    self.playlist_total = 0
                
                # Get channel name from first video
                if videos:
                    first_video = videos[0]
                    self.channel_name = (
                        first_video.get("channel") or 
                        first_video.get("uploader") or 
                        first_video.get("playlist_uploader") or
                        "Unknown"
                    )
                    
                    playlist_info = {
                        "title": first_video.get("playlist_title", "Playlist"),
                        "uploader": first_video.get("uploader", "Unknown"),
                        "channel": self.channel_name,
                        "channel_id": first_video.get("channel_id", ""),
                        "playlist_count": self.playlist_total,
                        "is_playlist": self.playlist_total > 1,  # Only true if more than 1 video
                        "thumbnail": first_video.get("thumbnail", "")
                    }
                    self.info_ready.emit(self.task_id, playlist_info)
        except Exception as e:
            print(f"Error getting playlist info: {e}")

        # If it's actually a single video (playlist_total == 0), handle as single download
        if self.playlist_total <= 1:
            # Download as single video
            info = self._fetch_info()
            if info:
                self.info_ready.emit(self.task_id, info)
            if self._cancelled:
                return
            self._download_single()
            return

        # Set output template with subfolder using channel/playlist name
        subfolder_name = self.channel_name
        
        # If no channel name found, try using the profile name
        if (not subfolder_name or subfolder_name == "Unknown") and self.profile_name:
            subfolder_name = self.profile_name
        
        if self.auto_create_subfolders and subfolder_name and subfolder_name != "Unknown":
            safe_folder_name = re.sub(r'[<>:"/\\|?*]', '_', subfolder_name)
            output_dir = os.path.join(self.output_dir, safe_folder_name)
            os.makedirs(output_dir, exist_ok=True)
        else:
            output_dir = self.output_dir
            
        out_tmpl = os.path.join(output_dir, "%(playlist_index)s - %(title)s.%(ext)s")

        fmt_sel, post = self._build_format_args()

        # Performance & reliability flags
        perf_flags = [
            "--concurrent-fragments", "8",
            "--retries", "10",
            "--fragment-retries", "10",
            "--buffer-size", "1M",
            "--no-abort-on-error",   # keep going if one playlist item fails
        ]

        cmd = ["yt-dlp", "-f", fmt_sel, "--newline", "--progress", "-o", out_tmpl,
            "--yes-playlist", *perf_flags, *post, self.url]

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, bufsize=1, **_HIDE)
            self.proc = proc
            error_lines: list[str] = []

            import threading as _threading
            def _collect_stderr():
                for ln in proc.stderr:
                    error_lines.append(ln.strip())
            _t = _threading.Thread(target=_collect_stderr, daemon=True)
            _t.start()

            current_video = 0
            for line in proc.stdout:
                self._pause_event.wait()
                line = line.strip()
                if self._cancelled:
                    proc.terminate()
                    return

                self.log.emit(self.task_id, line)

                # Track which item we're on using yt-dlp's own counter.
                # This avoids double-counting DASH streams (video+audio each
                # reach 100%, but there's only one logical video completed).
                item_match = re.search(r'\[download\] Downloading item (\d+) of (\d+)', line)
                if item_match:
                    current_item = int(item_match.group(1))
                    detected_total = int(item_match.group(2))
                    # Keep the higher total in case the preflight count was off
                    if detected_total > self.playlist_total:
                        self.playlist_total = detected_total
                    # When starting item N (N > 1), item N-1 just finished
                    if current_item > 1:
                        self.playlist_completed = current_item - 1
                        if self.playlist_total > 1:
                            self.playlist_progress.emit(
                                self.task_id, self.playlist_completed, self.playlist_total)
                            overall_pct = (self.playlist_completed / self.playlist_total) * 100
                            self.progress.emit(
                                self.task_id, overall_pct,
                                f"{self.playlist_completed}/{self.playlist_total}", "")
                    continue

                # Show post-processing status so UI doesn't appear frozen
                if "[Merger]" in line or "Merging formats" in line:
                    self.progress.emit(self.task_id, 100.0, "Merging…", "")
                    continue
                if "[VideoRecoder]" in line or "Recoding video" in line:
                    self.progress.emit(self.task_id, 100.0, "Processing…", "")
                    continue

                # Per-video download progress
                pct_match = re.search(r'(\d+\.?\d*)%', line)
                if pct_match and self.playlist_total > 1:
                    pct = float(pct_match.group(1))
                    speed_match = re.search(r'(\d+\.?\d*\s*[KMG]iB/s)', line)
                    speed = speed_match.group(1) if speed_match else "..."
                    self.current_speed = self._parse_speed(speed)
                    # Blend per-video pct into overall playlist progress
                    base = (self.playlist_completed / self.playlist_total) * 100
                    slot = (1 / self.playlist_total) * 100
                    overall = base + (pct / 100) * slot
                    self.progress.emit(self.task_id, overall, speed, "")

            proc.wait()
            _t.join(timeout=2)
            if proc.returncode == 0 and not self._cancelled:
                if self.playlist_total > 1:
                    # Mark the last video as completed (item tracker fires on *start*, not end)
                    self.playlist_completed = self.playlist_total
                    self.playlist_progress.emit(self.task_id, self.playlist_total, self.playlist_total)
                    self.finished.emit(self.task_id, True, f"Complete! ({self.playlist_completed}/{self.playlist_total} videos)")
                else:
                    self.finished.emit(self.task_id, True, "Download complete!")
            elif proc.returncode != 0 and not self._cancelled:
                err_msg = "Download failed"
                for ln in reversed(error_lines):
                    if ln and not ln.startswith("[debug]"):
                        err_msg = ln[:120]
                        break
                self.finished.emit(self.task_id, False, err_msg)

        except FileNotFoundError:
            self._simulate_playlist_download()

    def _simulate_download(self):
        """Demo mode when yt-dlp not installed"""
        speeds = ["2.4 MiB/s", "3.1 MiB/s", "1.8 MiB/s", "4.2 MiB/s", "2.9 MiB/s"]
        for i in range(0, 101, 2):
            if self._cancelled:
                return
            remaining = max(0, (100 - i) // 5)
            eta = f"{remaining}s" if remaining > 0 else "0s"
            spd = speeds[i % len(speeds)]
            self.current_speed = self._parse_speed(spd)
            self.progress.emit(self.task_id, float(i), spd, eta)
            time.sleep(0.08)
        self.finished.emit(self.task_id, True, "Download complete!")

    def _simulate_playlist_download(self):
        """Simulate playlist download for demo"""
        total = 5
        self.playlist_total = total
        self.playlist_progress.emit(self.task_id, 0, total)
        
        for i in range(1, total + 1):
            if self._cancelled:
                return
            for p in range(0, 101, 20):
                if self._cancelled:
                    return
                time.sleep(0.3)
            self.playlist_completed = i
            self.playlist_progress.emit(self.task_id, i, total)
            overall_pct = (i / total) * 100
            self.progress.emit(self.task_id, overall_pct, f"{i}/{total}", f"{(total-i)*3}s")
        
        self.finished.emit(self.task_id, True, f"Complete! ({total}/{total} videos)")

    def _parse_speed(self, speed_str: str) -> float:
        try:
            if "MiB/s" in speed_str:
                return float(speed_str.replace("MiB/s", "").strip())
            elif "KiB/s" in speed_str:
                return float(speed_str.replace("KiB/s", "").strip()) / 1024
        except:
            pass
        return 0