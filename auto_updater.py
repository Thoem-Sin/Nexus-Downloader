"""
Auto-updater for Nexus Downloader
- GitHub Releases integration
- Solid-card dialogs matching SettingsDialog / _NoInternetDialog theme
"""

import os
import sys
import requests
import subprocess
import shutil
import tempfile
from pathlib import Path
from packaging import version
from PySide6.QtCore import QThread, Signal, Qt, QTimer, QRect
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                               QLabel, QPushButton, QFrame, QProgressBar,
                               QWidget, QGraphicsDropShadowEffect, QScrollArea)
from PySide6.QtGui import QFont, QColor, QLinearGradient, QPainter, QBrush, QPainterPath

from themes import DARK_THEME


# ── Shared card constants (mirrors settings_dialog.py) ───────────────────────
_FONT   = "Inter"
_F_BODY = 9
_F_HEAD = 11
MARGIN  = 18          # transparent window margin so drop-shadow fits


# ── Gradient progress bar (unchanged — needed for download progress) ──────────
class GradientProgressBar(QProgressBar):
    def __init__(self, theme=None, parent=None):
        super().__init__(parent)
        self.setFixedHeight(7)
        self.setTextVisible(False)
        self._theme = theme or DARK_THEME

    def update_theme(self, theme: dict):
        self._theme = theme
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()

        bg = QPainterPath()
        bg.addRoundedRect(r, 3, 3)
        p.fillPath(bg, QColor(self._theme["progress_bg"]))

        if self.value() > 0:
            fw = int(r.width() * self.value() / 100.0)
            grad = QLinearGradient(0, 0, fw, 0)
            grad.setColorAt(0, QColor(self._theme["gradient_start"]))
            grad.setColorAt(1, QColor(self._theme["gradient_end"]))
            fp = QPainterPath()
            fp.addRoundedRect(QRect(0, 0, fw, r.height()), 3, 3)
            p.fillPath(fp, QBrush(grad))


# ── Shared solid-card builder ─────────────────────────────────────────────────
def _make_card(dialog: QDialog, width: int, height: int, theme: dict):
    """
    Attach a drop-shadow card to *dialog* using the MARGIN inset pattern.
    Returns (card QWidget, root QVBoxLayout of card).
    """
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(22)
    shadow.setOffset(0, 4)
    shadow.setColor(QColor(0, 0, 0, 160))

    dialog.setFixedSize(width + MARGIN * 2, height + MARGIN * 2)

    card = QWidget(dialog)
    card.setGeometry(MARGIN, MARGIN, width, height)
    card.setObjectName("dlg_card")
    card.setGraphicsEffect(shadow)

    root = QVBoxLayout(card)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    return card, root


def _card_stylesheet(theme: dict, accent: str = None) -> str:
    t = theme
    a = accent or t.get("accent", "#7C6AF7")
    return f"""
        QWidget#dlg_card {{
            background: {t['bg_card']};
            border: 1px solid {t['border']};
            border-radius: 14px;
        }}
        QWidget#dlg_header, QWidget#dlg_footer, QWidget#dlg_body,
        QWidget#dlg_inner, QFrame#dlg_divider {{
            background: transparent;
        }}
        QFrame#dlg_divider {{
            color: {t['border']}; background: {t['border']};
            max-height: 1px; border: none;
        }}
        QLabel {{
            background: transparent; border: none;
            color: {t['text_primary']}; font-size: {_F_BODY}pt;
        }}
        QLabel#lbl_muted   {{ color: {t['text_muted']}; }}
        QLabel#lbl_sub     {{ color: {t['text_secondary']}; }}
        QLabel#lbl_accent  {{ color: {a}; font-weight: bold; }}
        QLabel#lbl_title   {{ font-size: {_F_HEAD}pt; font-weight: bold; }}
        QPushButton#btn_close {{
            background: {t['bg_tertiary']}; border: 1px solid {t['border']};
            border-radius: 7px; color: {t['text_primary']}; font-size: {_F_BODY}pt;
        }}
        QPushButton#btn_close:hover {{
            background: #EF4444; border-color: #EF4444; color: white;
        }}
        QPushButton#btn_secondary {{
            background: {t['bg_tertiary']}; border: 1px solid {t['border']};
            border-radius: 7px; color: {t['text_primary']}; font-size: {_F_BODY}pt;
        }}
        QPushButton#btn_secondary:hover {{
            background: {t['bg_primary']}; color: {t['text_primary']};
        }}
        QPushButton#btn_primary {{
            background: {a}; border: none;
            border-radius: 7px; color: white;
            font-size: {_F_BODY}pt; font-weight: bold;
        }}
        QPushButton#btn_primary:hover {{ background: #9580FF; }}
        QPushButton#btn_primary:disabled {{
            background: {t['bg_tertiary']}; color: {t['text_muted']};
        }}
        QScrollArea {{ background: transparent; border: none; }}
        QScrollBar:vertical {{
            background: transparent; width: 5px; border-radius: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {t.get('scrollbar', 'rgba(128,128,128,0.4)')};
            border-radius: 2px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {t.get('scrollbar_hover', 'rgba(128,128,128,0.6)')};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QFrame#notes_frame {{
            background: {t['bg_secondary']};
            border: 1px solid {t['border']};
            border-radius: 8px;
        }}
        QFrame#version_frame {{
            background: {t['bg_secondary']};
            border: 1px solid {t['border']};
            border-radius: 10px;
        }}
    """


def _divider():
    f = QFrame(); f.setFrameShape(QFrame.HLine); f.setObjectName("dlg_divider")
    return f


def _header_widget(title: str, icon: str, close_slot, height=46):
    hdr = QWidget(); hdr.setObjectName("dlg_header"); hdr.setFixedHeight(height)
    lay = QHBoxLayout(hdr); lay.setContentsMargins(16, 0, 12, 0); lay.setSpacing(8)
    if icon:
        ic = QLabel(icon); ic.setFont(QFont("Segoe UI Emoji", 13)); lay.addWidget(ic)
    lbl = QLabel(title); lbl.setObjectName("lbl_title")
    lbl.setFont(QFont(_FONT, _F_HEAD, QFont.Bold)); lay.addWidget(lbl)
    lay.addStretch()
    btn = QPushButton("✕"); btn.setObjectName("btn_close")
    btn.setFixedSize(28, 28); btn.setCursor(Qt.PointingHandCursor)
    btn.clicked.connect(close_slot); lay.addWidget(btn)
    return hdr


# ── InfoDialog ────────────────────────────────────────────────────────────────
class InfoDialog(QDialog):
    """Replaces QMessageBox — solid card, 9 pt fonts, same theme as settings."""

    _ICONS = {
        "info":    ("ℹ️",  "#3B82F6"),
        "success": ("✅", "#10B981"),
        "warning": ("⚠️",  "#F59E0B"),
        "error":   ("❌", "#EF4444"),
    }

    def __init__(self, title: str, message: str, parent=None, theme=None, kind: str = "info"):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self._theme   = theme or DARK_THEME
        self._title   = title
        self._message = message
        self._kind    = kind if kind in self._ICONS else "info"
        self._drag_pos = None

        self.card, root = _make_card(self, 380, 180, self._theme)

        emoji, _ = self._ICONS[self._kind]
        root.addWidget(_header_widget(title, emoji, self.accept))
        root.addWidget(_divider())
        root.addWidget(self._build_body(), 1)
        root.addWidget(_divider())
        root.addWidget(self._build_footer())

        self.card.setStyleSheet(_card_stylesheet(self._theme))

    def _build_body(self):
        body = QWidget(); body.setObjectName("dlg_body")
        lay = QVBoxLayout(body); lay.setContentsMargins(16, 12, 16, 12)
        lbl = QLabel(self._message); lbl.setObjectName("lbl_sub")
        lbl.setFont(QFont(_FONT, _F_BODY)); lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(lbl)
        return body

    def _build_footer(self):
        ftr = QWidget(); ftr.setObjectName("dlg_footer"); ftr.setFixedHeight(46)
        lay = QHBoxLayout(ftr); lay.setContentsMargins(14, 6, 14, 6)
        lay.setSpacing(8); lay.addStretch()
        ok = QPushButton("OK"); ok.setObjectName("btn_primary")
        ok.setFixedSize(76, 30); ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(self.accept); lay.addWidget(ok)
        return ftr

    def update_theme(self, theme: dict):
        self._theme = theme
        self.card.setStyleSheet(_card_stylesheet(theme))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self._drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() == Qt.LeftButton:
            self.move(self.pos() + e.globalPosition().toPoint() - self._drag_pos)
            self._drag_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e): self._drag_pos = None

    @staticmethod
    def information(parent, title, message, theme=None):
        InfoDialog(title, message, parent, theme, "info").exec()

    @staticmethod
    def success(parent, title, message, theme=None):
        InfoDialog(title, message, parent, theme, "success").exec()

    @staticmethod
    def warning(parent, title, message, theme=None):
        InfoDialog(title, message, parent, theme, "warning").exec()

    @staticmethod
    def error(parent, title, message, theme=None):
        InfoDialog(title, message, parent, theme, "error").exec()


# ── Update checker / downloader threads (unchanged logic) ─────────────────────
class UpdateChecker(QThread):
    update_available = Signal(dict)

    def __init__(self, current_version, owner="Thoem-Sin", repo="Nexus-Downloader"):
        super().__init__()
        self.current_version = current_version
        self.owner = owner
        self.repo = repo
        self.api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    def run(self):
        try:
            resp = requests.get(self.api_url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            latest = data["tag_name"].lstrip("v")
            if version.parse(latest) > version.parse(self.current_version):
                url = next(
                    (a["browser_download_url"] for a in data.get("assets", [])
                     if a["name"].endswith(".exe")), None)
                self.update_available.emit({
                    "available": True,
                    "current_version": self.current_version,
                    "latest_version": latest,
                    "download_url": url,
                    "release_notes": data.get("body", "No release notes provided."),
                    "published_at": data.get("published_at", ""),
                })
            else:
                self.update_available.emit({"available": False})
        except Exception as e:
            self.update_available.emit({"available": False, "error": str(e)})


class UpdateDownloader(QThread):
    progress = Signal(int, int)
    finished = Signal(bool, str)

    def __init__(self, download_url):
        super().__init__()
        self.download_url = download_url

    def run(self):
        try:
            save_path = os.path.join(tempfile.gettempdir(), "NexusDownloader-update.exe")
            resp = requests.get(self.download_url, timeout=60, stream=True)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            done = 0
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    if chunk:
                        f.write(chunk); done += len(chunk)
                        if total: self.progress.emit(done, total)
            self.finished.emit(True, save_path)
        except Exception as e:
            self.finished.emit(False, str(e))


class UpdateInstaller:
    @staticmethod
    def install_update(exe_path):
        try:
            if not getattr(sys, "frozen", False):
                return False
            cur = sys.executable
            shutil.copy2(cur, cur + ".backup")
            shutil.copy2(exe_path, cur)
            try: os.remove(exe_path)
            except: pass
            if sys.platform == "win32":
                bat = f"@echo off\ntimeout /t 2 /nobreak >nul\nstart \"\" \"{cur}\"\nexit\n"
                bp = os.path.join(tempfile.gettempdir(), "restart.bat")
                open(bp, "w").write(bat)
                subprocess.Popen(["cmd", "/c", bp], shell=True,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except Exception as e:
            print(f"Install error: {e}"); return False


# ── UpdateNotificationDialog ──────────────────────────────────────────────────
class UpdateNotificationDialog(QDialog):

    def __init__(self, update_info, parent=None, theme=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self._theme      = theme or DARK_THEME
        self.update_info = update_info
        self._drag_pos   = None

        self.card, root = _make_card(self, 460, 480, self._theme)

        root.addWidget(_header_widget("Update Available", "🎉", self.reject))
        root.addWidget(_divider())
        root.addWidget(self._build_body(), 1)
        root.addWidget(_divider())
        root.addWidget(self._build_footer())

        self.card.setStyleSheet(_card_stylesheet(self._theme))

    # ── body ──────────────────────────────────────────────────────────────────
    def _build_body(self):
        body = QWidget(); body.setObjectName("dlg_body")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(16, 12, 16, 10); lay.setSpacing(10)
        lay.addWidget(self._version_card())
        lay.addWidget(self._whatsnew(), 1)
        return body

    def _version_card(self):
        frame = QFrame(); frame.setObjectName("version_frame")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(20, 14, 20, 14); lay.setSpacing(0)

        def _ver_block(label_text, version_text, name):
            w = QWidget(); vl = QVBoxLayout(w)
            vl.setSpacing(3); vl.setAlignment(Qt.AlignCenter)
            lbl = QLabel(label_text); lbl.setObjectName("lbl_muted")
            lbl.setFont(QFont(_FONT, _F_BODY)); lbl.setAlignment(Qt.AlignCenter)
            ver = QLabel(version_text); ver.setObjectName(name)
            ver.setFont(QFont(_FONT, 18, QFont.Bold)); ver.setAlignment(Qt.AlignCenter)
            vl.addWidget(lbl); vl.addWidget(ver)
            return w, ver

        cur_w, self.cur_lbl = _ver_block(
            "Current", f"v{self.update_info.get('current_version','?')}", "")
        new_w, self.new_lbl = _ver_block(
            "New",     f"v{self.update_info.get('latest_version','?')}",  "lbl_accent")

        arrow = QLabel("→"); arrow.setObjectName("lbl_muted")
        arrow.setFont(QFont("Segoe UI", 22)); arrow.setAlignment(Qt.AlignCenter)

        lay.addWidget(cur_w, 1); lay.addWidget(arrow); lay.addWidget(new_w, 1)
        return frame

    def _whatsnew(self):
        outer = QWidget()
        lay = QVBoxLayout(outer); lay.setContentsMargins(0,0,0,0); lay.setSpacing(6)

        hdr = QHBoxLayout(); hdr.setSpacing(6)
        ic = QLabel("📝"); ic.setFont(QFont("Segoe UI Emoji", 11))
        tl = QLabel("What's New"); tl.setObjectName("lbl_title")
        tl.setFont(QFont(_FONT, _F_BODY, QFont.Bold))
        hdr.addWidget(ic); hdr.addWidget(tl); hdr.addStretch()
        lay.addLayout(hdr)

        frame = QFrame(); frame.setObjectName("notes_frame")
        fl = QVBoxLayout(frame); fl.setContentsMargins(12, 8, 12, 8)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        il = QVBoxLayout(inner); il.setContentsMargins(0,0,0,0)
        notes = QLabel(self.update_info.get("release_notes", "No release notes provided."))
        notes.setObjectName("lbl_sub"); notes.setWordWrap(True)
        notes.setFont(QFont(_FONT, _F_BODY))
        notes.setTextInteractionFlags(Qt.TextSelectableByMouse)
        il.addWidget(notes); il.addStretch()

        scroll.setWidget(inner)
        fl.addWidget(scroll)
        frame.setMinimumHeight(160)
        lay.addWidget(frame, 1)
        return outer

    # ── footer ────────────────────────────────────────────────────────────────
    def _build_footer(self):
        ftr = QWidget(); ftr.setObjectName("dlg_footer"); ftr.setFixedHeight(50)
        lay = QHBoxLayout(ftr); lay.setContentsMargins(14, 8, 14, 8); lay.setSpacing(8)
        lay.addStretch()

        for label, result, name in [
            ("Skip",         2, "btn_secondary"),
            ("Remind Later", 0, "btn_secondary"),
            ("Install Now",  1, "btn_primary"),
        ]:
            btn = QPushButton(label); btn.setObjectName(name)
            btn.setFixedHeight(30); btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, r=result: self.done(r))
            lay.addWidget(btn)
        return ftr

    def update_theme(self, theme: dict):
        self._theme = theme
        self.card.setStyleSheet(_card_stylesheet(theme))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self._drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() == Qt.LeftButton:
            self.move(self.pos() + e.globalPosition().toPoint() - self._drag_pos)
            self._drag_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e): self._drag_pos = None

    @staticmethod
    def _fmt_size(b):
        for u in ["B","KB","MB","GB"]:
            if b < 1024: return f"{b:.1f} {u}"
            b /= 1024
        return f"{b:.1f} TB"


# ── ProgressDialog ────────────────────────────────────────────────────────────
class ProgressDialog(QDialog):

    def __init__(self, parent=None, theme=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self._theme     = theme or DARK_THEME
        self.cancel_flag = False
        self._drag_pos  = None

        self.card, root = _make_card(self, 400, 210, self._theme)

        root.addWidget(self._build_header())
        root.addWidget(_divider())
        root.addWidget(self._build_body(), 1)

        self.card.setStyleSheet(_card_stylesheet(self._theme))

    def _build_header(self):
        hdr = QWidget(); hdr.setObjectName("dlg_header"); hdr.setFixedHeight(46)
        lay = QHBoxLayout(hdr); lay.setContentsMargins(16, 0, 12, 0); lay.setSpacing(8)
        ic = QLabel("⬇️"); ic.setFont(QFont("Segoe UI Emoji", 13)); lay.addWidget(ic)
        tl = QLabel("Downloading Update"); tl.setObjectName("lbl_title")
        tl.setFont(QFont(_FONT, _F_HEAD, QFont.Bold)); lay.addWidget(tl)
        lay.addStretch()
        self.cancel_btn = QPushButton("Cancel"); self.cancel_btn.setObjectName("btn_secondary")
        self.cancel_btn.setFixedSize(70, 28); self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._on_cancel); lay.addWidget(self.cancel_btn)
        return hdr

    def _build_body(self):
        body = QWidget(); body.setObjectName("dlg_body")
        lay = QVBoxLayout(body); lay.setContentsMargins(20, 16, 20, 18); lay.setSpacing(10)

        self.status_label = QLabel("Preparing download...")
        self.status_label.setObjectName("lbl_sub")
        self.status_label.setFont(QFont(_FONT, _F_BODY))
        self.status_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.status_label)

        self.progress_bar = GradientProgressBar(self._theme)
        self.progress_bar.setRange(0, 100)
        lay.addWidget(self.progress_bar)

        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("lbl_muted")
        self.percent_label.setFont(QFont(_FONT, _F_BODY))
        self.percent_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.percent_label)

        return body

    def update_theme(self, theme: dict):
        self._theme = theme
        self.progress_bar.update_theme(theme)
        self.card.setStyleSheet(_card_stylesheet(theme))

    def _on_cancel(self):
        self.cancel_flag = True
        self.status_label.setText("Cancelling...")
        self.cancel_btn.setEnabled(False)

    def update_progress(self, downloaded, total):
        if self.cancel_flag: return
        pct = int(downloaded * 100 / total) if total else 0
        self.progress_bar.setValue(pct)
        self.percent_label.setText(f"{pct}%")
        self.status_label.setText(
            f"Downloading: {self._fmt(downloaded)} / {self._fmt(total)}")

    @staticmethod
    def _fmt(b):
        for u in ["B","KB","MB","GB"]:
            if b < 1024: return f"{b:.1f} {u}"
            b /= 1024
        return f"{b:.1f} TB"

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self._drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() == Qt.LeftButton:
            self.move(self.pos() + e.globalPosition().toPoint() - self._drag_pos)
            self._drag_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e): self._drag_pos = None


# ── UpdateManager (logic unchanged) ──────────────────────────────────────────
class UpdateManager:
    def __init__(self, current_version="1.0.0", owner="Thoem-Sin",
                 repo="Nexus-Downloader", parent=None, theme=None):
        self.current_version = current_version
        self.owner  = owner
        self.repo   = repo
        self.parent = parent
        self.theme  = theme

    def check_for_updates(self, background=True):
        self._background_check = background
        self.checker = UpdateChecker(self.current_version, self.owner, self.repo)
        self.checker.update_available.connect(self._on_update_found)
        if background:
            self.checker.start()
        else:
            self.checker.run()

    def _on_update_found(self, info):
        if info.get("available"):
            dlg = UpdateNotificationDialog(info, self.parent, self.theme)
            if dlg.exec() == 1:
                self._start_download(info.get("download_url"))
        elif not getattr(self, "_background_check", True) and self.parent:
            InfoDialog.information(
                self.parent, "No Updates",
                f"You're using the latest version (v{self.current_version})",
                self.theme)

    def _start_download(self, url):
        if not url:
            InfoDialog.warning(self.parent, "Error", "Download URL not found", self.theme)
            return
        self.progress   = ProgressDialog(self.parent, self.theme)
        self.downloader = UpdateDownloader(url)
        self.downloader.progress.connect(self.progress.update_progress)
        self.downloader.finished.connect(self._on_download_finished)
        self.downloader.start()
        self.progress.exec()

    def _on_download_finished(self, success, path):
        self.progress.close()
        if success:
            if UpdateInstaller.install_update(path):
                InfoDialog.success(self.parent, "Update Complete",
                                   "Update installed! The app will restart.", self.theme)
            else:
                InfoDialog.error(self.parent, "Install Failed",
                                 "Failed to install update.", self.theme)
        else:
            InfoDialog.error(self.parent, "Download Failed",
                             f"Failed to download: {path}", self.theme)


# ── Setup helper ──────────────────────────────────────────────────────────────
def setup_auto_updater(main_window, current_version="1.0.0"):
    manager = UpdateManager(
        current_version=current_version,
        owner="Thoem-Sin",
        repo="Nexus-Downloader",
        parent=main_window,
        theme=getattr(main_window, "_theme", None),
    )
    QTimer.singleShot(3000, lambda: manager.check_for_updates(background=True))
    return manager


# ── GlassCard stub (kept for any other file that imports it) ──────────────────
class GlassCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)


__all__ = ["setup_auto_updater", "UpdateManager", "InfoDialog"]