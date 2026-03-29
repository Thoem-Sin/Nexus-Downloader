"""Main application window"""

import os
import sys
import time
import socket
import subprocess
import shutil
from pathlib import Path
from typing import Dict
from auto_updater import setup_auto_updater, UpdateManager, InfoDialog
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QPushButton, QFrame, QScrollArea,
                               QFileDialog, QTextEdit, QDialog, QApplication,
                               QGraphicsOpacityEffect, QProgressBar)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QAbstractAnimation, QPoint, QEasingCurve
from PySide6.QtGui import QFont, QColor, QIcon, QPixmap, QPalette

from themes import DARK_THEME, LIGHT_THEME
from settings_manager import SettingsManager
from download_worker import DownloadWorker, FetchWorker
from queue_manager import DownloadQueueManager
from channel_scraper import ChannelScraperWorker, is_channel_or_profile_url
from widgets import (GlassCard, AnimatedIcon, LogoAnimatedIcon, ModernDownloadCard,
                    ModernFormatPanel, ModernStatsBar, ScraperWindow,
                    FailedDownloadsDialog)
# ── Single source of truth for the app version ────────────────────────────────
APP_VERSION = "1.0.0"   # ← bump this every release, then rebuild + push to GitHub


class ModernMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings_manager = SettingsManager()
        self._is_dark = True
        self._theme = DARK_THEME
        self._tasks: Dict[str, Dict] = {}
        self._cards: Dict[str, ModernDownloadCard] = {}
        self._workers: Dict[str, DownloadWorker] = {}
        self._fetch_workers: Dict[str, FetchWorker] = {}   # parallel metadata probes
        self._pending_downloads: Dict[str, dict] = {}      # settings held until fetch completes
        self._output_dir = self.settings_manager.get("output_dir", str(Path.home() / "Downloads"))
        self._counter = 0
        self._total_speed = 0.0
        self._global_paused = False
        self._scraper_worker = None  # type: ChannelScraperWorker | None
        self._scraper_win = None     # type: ScraperWindow | None
        self._scrape_debounce = QTimer()
        self._scrape_debounce.setSingleShot(True)
        self._scrape_debounce.setInterval(800)   # 800ms after user stops typing
        self._scrape_debounce.timeout.connect(self._debounced_scrape_check)
        self._ignore_url_change = False   # guard against re-entrant triggers
        
        max_concurrent = int(self.settings_manager.get("concurrent_downloads", 3))
        self.queue_manager = DownloadQueueManager(max_concurrent)
        self.queue_manager.task_added.connect(self._on_task_added)
        self.queue_manager.task_completed.connect(self._on_queue_task_completed)
        
        self.setWindowTitle("Nexus Downloader")
        # App icon — used in taskbar, Alt+Tab, and bundled EXE
        _icon_path = str(Path(__file__).parent / "Icon.ico")
        if Path(_icon_path).exists():
            self.setWindowIcon(QIcon(_icon_path))
        self.setMinimumSize(500, 650)
        self.resize(750, 900)
        
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self._setup_ui()
        self._apply_global_theme()
        
        # Start capacity update timer
        self.capacity_timer = QTimer()
        self.capacity_timer.timeout.connect(self._update_capacity)
        self.capacity_timer.start(2000)  # Update every 2 seconds
        self._update_capacity()

        # ── Auto-check for updates 4 s after launch (background, silent) ──
        self.update_manager = UpdateManager(
            current_version=APP_VERSION,
            owner="Thoem-Sin",
            repo="Nexus-Downloader",
            parent=self,
            theme=self._theme,
        )
        QTimer.singleShot(4000, lambda: self.update_manager.check_for_updates(background=True))

        # ── Periodic license re-check every 60 min (catches mid-session revocations) ──
        self._license_check_timer = QTimer(self)
        self._license_check_timer.timeout.connect(self._periodic_license_check)
        self._license_check_timer.start(60 * 60 * 1000)   # 60 minutes

    def _periodic_license_check(self):
        """Re-validate license against the server every hour.
        If revoked/expired, stop all downloads and show the license dialog."""
        from license_client import validate_license
        from license_dialog import LicenseDialog
        result = validate_license(force_online=True)
        if result.get("ok"):
            self.refresh_footer_license()
            return
        status = result.get("status", "")
        # Block: stop all active downloads
        self._stop_all()
        self.refresh_footer_license()
        # Show non-closable license dialog
        dlg = LicenseDialog(parent=self, allow_close=False)
        if dlg.exec():
            self.refresh_footer_license()
        else:
            self.close()

    def _check_for_updates(self):
        """Check for updates manually (from toolbar button)"""
        try:
            self.update_manager.check_for_updates(background=False)
        except Exception as e:
            print(f"Error checking for updates: {e}")
            InfoDialog.error(self, "Update Error", f"Could not check for updates:\n{e}", self._theme)
        
    def _setup_ui(self):
        central = QWidget()
        central.setObjectName("central")
        # Make background 100% transparent
        central.setStyleSheet("QWidget#central { background: transparent; }")
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)
        
        self.main_container = GlassCard()
        container_layout = QVBoxLayout(self.main_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        container_layout.addWidget(self._build_titlebar())
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 16, 20, 16)
        #content_layout.setSpacing(16)
        
        content_layout.addWidget(self._build_hero_section())
        
        self.format_panel = ModernFormatPanel(self._theme)

        # Format row: format panel + folder picker side by side
        format_row = QHBoxLayout()
        format_row.setContentsMargins(0, 0, 0, 0)
        format_row.setSpacing(8)
        format_row.addWidget(self.format_panel)

        self.folder_btn = QPushButton("📁 Output Folder")
        self.folder_btn.setObjectName("secondary_button")
        self.folder_btn.setFixedHeight(36)
        self.folder_btn.setCursor(Qt.PointingHandCursor)
        self.folder_btn.setFont(QFont("Inter", 9))
        self.folder_btn.clicked.connect(self._choose_folder)
        format_row.addWidget(self.folder_btn)

        format_row_widget = QWidget()
        format_row_widget.setLayout(format_row)
        content_layout.addWidget(format_row_widget)
        
        content_layout.addWidget(self._build_downloads_section(), 1)
        
        container_layout.addWidget(content_widget)
        
        # Create bottom bar with stats and capacity
        bottom_bar = self._build_bottom_bar()
        container_layout.addWidget(bottom_bar)

        # Footer strip — version + copyright
        self.footer_bar = self._build_footer_bar()
        container_layout.addWidget(self.footer_bar)

        root.addWidget(self.main_container)
        self.setCentralWidget(central)
    
    def _build_bottom_bar(self):
        """Build bottom bar combining stats and capacity"""
        bar = QWidget()
        bar.setObjectName("bottom_bar")
        bar.setFixedHeight(70)
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 8, 20, 8)
        #layout.setSpacing(20)
        
        # Stats bar (left side)
        self.stats_bar = ModernStatsBar(self._theme)
        layout.addWidget(self.stats_bar, 2)
        
        # Divider
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.VLine)
        divider.setFixedWidth(1)
        layout.addWidget(divider)
        
        # Capacity display (right side)
        capacity_widget = self._build_capacity_widget()
        layout.addWidget(capacity_widget, 1)
        
        return bar
    
    def _build_footer_bar(self) -> QWidget:
        """Footer strip: license status (left)  ·  version + copyright (right)."""
        bar = QWidget()
        bar.setObjectName("footer_bar")
        bar.setFixedHeight(26)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(6)

        # ── Left: license status + remaining days ────────────────────────
        from license_client import validate_license
        lic = validate_license(force_online=False)

        if lic.get("ok"):
            days = lic.get("days_left", 0)
            if days > 0:
                lic_text = f"✅ Licensed  ·  {days} days remaining"
                lic_obj   = "footer_lic_ok"
            else:
                lic_text = "✅ Licensed  ·  Lifetime"
                lic_obj   = "footer_lic_ok"
        else:
            status = lic.get("status", "invalid")
            if status == "no_key":
                lic_text = "⚠️ No License"
            elif status == "expired":
                lic_text = "❌ License Expired"
            else:
                lic_text = "❌ License Invalid"
            lic_obj = "footer_lic_warn"

        self.footer_lic_lbl = QLabel(lic_text)
        self.footer_lic_lbl.setObjectName(lic_obj)
        self.footer_lic_lbl.setFont(QFont("Inter", 9))

        layout.addWidget(self.footer_lic_lbl)
        layout.addStretch()

        # ── Right: version · copyright ───────────────────────────────────
        def _lbl(text):
            l = QLabel(text)
            l.setObjectName("footer_text")
            l.setFont(QFont("Inter", 9))
            return l

        layout.addWidget(_lbl(f"v{APP_VERSION}"))
        layout.addWidget(_lbl("  ·  "))
        layout.addWidget(_lbl("© Nexus Downloader"))

        return bar

    def refresh_footer_license(self):
        """Call this after a license is activated to refresh the footer label."""
        if not hasattr(self, 'footer_lic_lbl'):
            return
        from license_client import validate_license
        lic = validate_license(force_online=False)
        if lic.get("ok"):
            days = lic.get("days_left", 0)
            self.footer_lic_lbl.setText(
                f"✅ Licensed  ·  {days} days remaining" if days > 0
                else "✅ Licensed  ·  Lifetime"
            )
            self.footer_lic_lbl.setObjectName("footer_lic_ok")
        else:
            status = lic.get("status", "invalid")
            text = {
                "no_key":  "⚠️ No License",
                "expired": "❌ License Expired",
            }.get(status, "❌ License Invalid")
            self.footer_lic_lbl.setText(text)
            self.footer_lic_lbl.setObjectName("footer_lic_warn")
        # Re-apply theme so new objectName colour takes effect
        self._apply_global_theme()

    def _build_capacity_widget(self):
        """Build capacity display widget"""
        container = QWidget()
        container.setFixedWidth(280)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(4)
        
        # Header with icon and percent
        header_layout = QHBoxLayout()
        capacity_icon = QLabel("💾")
        capacity_icon.setObjectName("capacity_icon")
        capacity_icon.setFont(QFont("Segoe UI", 12))
        # Make icon selectable
        capacity_icon.setTextInteractionFlags(Qt.TextSelectableByMouse)
        header_layout.addWidget(capacity_icon)
        
        self.capacity_percent = QLabel("0%")
        self.capacity_percent.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        # Make percentage selectable
        self.capacity_percent.setTextInteractionFlags(Qt.TextSelectableByMouse)
        header_layout.addWidget(self.capacity_percent)
        
        header_layout.addStretch()
        
        # Used/Free info
        self.space_info = QLabel("0 GB used · 0 GB free")
        self.space_info.setObjectName("space_info")
        self.space_info.setFont(QFont("Inter", 8))
        # Make space info selectable
        self.space_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        header_layout.addWidget(self.space_info)
        
        layout.addLayout(header_layout)
        
        # Progress bar
        self.capacity_bar = QProgressBar()
        self.capacity_bar.setFixedHeight(4)
        self.capacity_bar.setTextVisible(False)
        layout.addWidget(self.capacity_bar)
        
        return container
    
    def _update_capacity(self):
        """Update storage capacity display"""
        try:
            # Resolve a valid path to measure — fall back to home/Downloads
            # if the saved output_dir no longer exists on disk.
            measure_path = self._output_dir
            if not os.path.exists(measure_path):
                fallback = str(Path.home() / "Downloads")
                os.makedirs(fallback, exist_ok=True)
                measure_path = fallback
                # Persist the corrected path so it stops erroring
                self._output_dir = fallback
                self.settings_manager.set("output_dir", fallback)

            # Use the drive root on Windows so shutil.disk_usage always has
            # something to measure even when the folder was just created.
            drive_root = os.path.splitdrive(measure_path)[0] or measure_path
            if drive_root and os.path.exists(drive_root):
                usage = shutil.disk_usage(drive_root)
            else:
                usage = shutil.disk_usage(measure_path)
            
            # Calculate percentages and sizes
            total_gb = usage.total / (1024**3)
            used_gb = usage.used / (1024**3)
            free_gb = usage.free / (1024**3)
            percent = (usage.used / usage.total) * 100
            
            # Update UI
            self.capacity_bar.setValue(int(percent))
            self.capacity_percent.setText(f"{percent:.1f}%")
            self.space_info.setText(f"{used_gb:.1f} GB used · {free_gb:.1f} GB free")
            
            # Change color if space is low
            if percent > 90:
                self.capacity_percent.setStyleSheet("color: #EF4444; font-weight: bold;")
                self.capacity_bar.setStyleSheet("""
                    QProgressBar {
                        background: rgba(255, 255, 255, 0.1);
                        border: none;
                        border-radius: 2px;
                    }
                    QProgressBar::chunk {
                        background: #EF4444;
                        border-radius: 2px;
                    }
                """)
            elif percent > 75:
                self.capacity_percent.setStyleSheet("color: #F59E0B; font-weight: bold;")
                self.capacity_bar.setStyleSheet("""
                    QProgressBar {
                        background: rgba(255, 255, 255, 0.1);
                        border: none;
                        border-radius: 2px;
                    }
                    QProgressBar::chunk {
                        background: #F59E0B;
                        border-radius: 2px;
                    }
                """)
            else:
                self.capacity_percent.setStyleSheet("color: #8B5CF6; font-weight: bold;")
                self.capacity_bar.setStyleSheet("""
                    QProgressBar {
                        background: rgba(255, 255, 255, 0.1);
                        border: none;
                        border-radius: 2px;
                    }
                    QProgressBar::chunk {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #8B5CF6, stop:1 #EC489A);
                        border-radius: 2px;
                    }
                """)
        except Exception as e:
            print(f"Error updating capacity: {e}")
    
    def _create_icon_button(self, icon_text: str, tooltip: str) -> QPushButton:
        btn = QPushButton(icon_text)
        btn.setObjectName("icon_button")
        btn.setFixedSize(36, 36)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tooltip)
        
        opacity_effect = QGraphicsOpacityEffect()
        opacity_effect.setOpacity(0.8)
        btn.setGraphicsEffect(opacity_effect)
        btn._opacity_effect = opacity_effect
        
        def on_enter():
            anim = QPropertyAnimation(btn._opacity_effect, b"opacity")
            anim.setDuration(150)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            
        def on_leave():
            anim = QPropertyAnimation(btn._opacity_effect, b"opacity")
            anim.setDuration(150)
            anim.setEndValue(0.8)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            
        btn.enterEvent = lambda e: on_enter()
        btn.leaveEvent = lambda e: on_leave()
        
        return btn
    
    def _create_action_button(self, text: str, style: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(f"{style}_button")
        btn.setFixedHeight(36)
        btn.setCursor(Qt.PointingHandCursor)
        
        opacity_effect = QGraphicsOpacityEffect()
        opacity_effect.setOpacity(0.9)
        btn.setGraphicsEffect(opacity_effect)
        btn._opacity_effect = opacity_effect
        
        def on_enter():
            anim = QPropertyAnimation(btn._opacity_effect, b"opacity")
            anim.setDuration(150)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            
        def on_leave():
            anim = QPropertyAnimation(btn._opacity_effect, b"opacity")
            anim.setDuration(150)
            anim.setEndValue(0.9)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            
        btn.enterEvent = lambda e: on_enter()
        btn.leaveEvent = lambda e: on_leave()
        
        return btn
    
    def _build_titlebar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(62)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 0, 10, 0)
        #layout.setSpacing(6)#
        
        logo_container = QWidget()
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setSpacing(6)
        
        _logo_path = str(Path(__file__).parent / "logo.png")
        self.logo_icon = LogoAnimatedIcon(logo_path=_logo_path, size=44)
        self.logo_icon.start_pulse()
        logo_layout.addWidget(self.logo_icon)
        
        logo_text = QLabel("Nexus Downloader")
        logo_text.setFont(QFont("Inter", 14, QFont.Weight.Bold))
        logo_text.setObjectName("logo_text")
        logo_layout.addWidget(logo_text)
        
        layout.addWidget(logo_container)
        layout.addStretch()
        
        settings_btn = self._create_icon_button("⚙️", "Settings")
        settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(settings_btn)

        
        update_btn = self._create_icon_button("🔄", "Check for Updates")
        update_btn.clicked.connect(self._check_for_updates)
        layout.addWidget(update_btn)

        self.theme_btn = self._create_icon_button("🌙", "Switch Theme")
        self.theme_btn.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_btn)
        
        minimize_btn = self._create_icon_button("─", "Minimize")
        minimize_btn.clicked.connect(self.showMinimized)
        layout.addWidget(minimize_btn)
        
        close_btn = self._create_icon_button("✕", "Close")
        close_btn.setObjectName("close_button")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        return bar
    
    def _build_hero_section(self) -> QWidget:
        hero = QWidget()
        hero.setObjectName("hero")
        layout = QVBoxLayout(hero)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)
        
        self.url_input = QTextEdit()
        self.url_input.setObjectName("url_input")
        self.url_input.setPlaceholderText(
            "Paste video or channel URLs (one per line):\n"
            "https://youtube.com/watch?v=...  ← single video\n"
            "https://youtube.com/@channel/    ← auto-opens channel scraper\n"
            "https://youtube.com/playlist?list=..."
        )
        self.url_input.setFont(QFont("Inter", 10))
        self.url_input.setFixedHeight(100)
        self.url_input.setAcceptRichText(False)
        self.url_input.textChanged.connect(self._on_url_input_changed)
        layout.addWidget(self.url_input)

        # Inline hint / error message shown below the URL box
        self.url_hint_label = QLabel("")
        self.url_hint_label.setObjectName("url_hint_label")
        self.url_hint_label.setFont(QFont("Inter", 9))
        self.url_hint_label.setAlignment(Qt.AlignCenter)
        self.url_hint_label.setFixedHeight(22)
        self.url_hint_label.hide()
        layout.addWidget(self.url_hint_label)

        # Timer to auto-hide the hint after 3 s
        self._hint_hide_timer = QTimer(self)
        self._hint_hide_timer.setSingleShot(True)
        self._hint_hide_timer.setInterval(3000)
        self._hint_hide_timer.timeout.connect(self._hide_url_hint)

        control_row = QHBoxLayout()
        control_row.setSpacing(8)
        
        paste_btn = self._create_action_button("Paste", "secondary")
        paste_btn.setObjectName("paste_button")
        paste_btn.clicked.connect(self._paste_url)
        control_row.addWidget(paste_btn)

        self.download_btn = self._create_action_button("Download All", "primary")
        self.download_btn.clicked.connect(self._start_download)
        control_row.addWidget(self.download_btn)

        self.global_control_btn = self._create_action_button("⏸ Pause All", "secondary")
        self.global_control_btn.setObjectName("pause_button")
        self.global_control_btn.clicked.connect(self._toggle_global_pause_resume)
        control_row.addWidget(self.global_control_btn)

        self.global_stop_btn = self._create_action_button("✕ Stop All", "secondary")
        self.global_stop_btn.setObjectName("stop_button")
        self.global_stop_btn.clicked.connect(self._stop_all)
        control_row.addWidget(self.global_stop_btn)
        
        layout.addLayout(control_row)
        
        return hero
    
    def _build_downloads_section(self) -> QWidget:
        section = QWidget()
        layout = QVBoxLayout(section)
        #layout.setSpacing(8)#
        
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        section_title = QLabel("Active Downloads")
        section_title.setObjectName("section_title")
        section_title.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        header_layout.addWidget(section_title)
        
        self.active_count = QLabel("0 active")
        self.active_count.setObjectName("active_count")
        self.active_count.setFont(QFont("Inter", 9))
        header_layout.addWidget(self.active_count)
        header_layout.addStretch()
        
        clear_btn = QPushButton("Clear Completed")
        clear_btn.setObjectName("ghost_button")
        clear_btn.setFont(QFont("Inter", 9))
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_finished)
        header_layout.addWidget(clear_btn)

        self.failed_btn = QPushButton("❌ Failed")
        self.failed_btn.setObjectName("failed_btn")
        self.failed_btn.setFont(QFont("Inter", 9))
        self.failed_btn.setCursor(Qt.PointingHandCursor)
        self.failed_btn.setVisible(False)   # hidden until there are failures
        self.failed_btn.clicked.connect(self._open_failed_dialog)
        header_layout.addWidget(self.failed_btn)
        
        layout.addWidget(header)
        
        scroll = QScrollArea()
        scroll.setObjectName("downloads_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.card_container = QWidget()
        self.card_container.setObjectName("card_container")
        self.cards_layout = QVBoxLayout(self.card_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()
        
        self.empty_state = QWidget()
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setAlignment(Qt.AlignCenter)
        
        empty_icon = QLabel("🎬")
        empty_icon.setFont(QFont("Segoe UI", 40))
        empty_icon.setAlignment(Qt.AlignCenter)
        
        empty_text = QLabel("No downloads yet\nPaste URLs above to get started")
        empty_text.setAlignment(Qt.AlignCenter)
        empty_text.setObjectName("empty_text")
        empty_text.setFont(QFont("Inter", 10))
        
        empty_layout.addWidget(empty_icon)
        empty_layout.addWidget(empty_text)
        self.cards_layout.insertWidget(0, self.empty_state)
        
        scroll.setWidget(self.card_container)
        layout.addWidget(scroll)
        
        return section
    
    def _apply_global_theme(self):
        t = self._theme
    
        self.setStyleSheet(f"""
            QWidget#central {{
                background: {t['bg_primary']};
            }}
            GlassCard {{
                background: {t['bg_card']};
                border-radius: 20px;
                border: 1px solid {t['border']};
            }}
            QLabel#logo_text {{
                color: {t['text_primary']};
            }}
            QPushButton#icon_button {{
                background: {t['bg_tertiary']};
                border: 1px solid {t['border']};
                border-radius: 10px;
                color: {t['text_primary']};
                font-size: 14px;
                min-width: 36px;
            }}
            QPushButton#icon_button:hover {{
                background: {t['accent']};
                color: white;
                border-color: {t['accent']};
            }}
            QPushButton#close_button {{
                background: {t['bg_tertiary']};
                border: 1px solid {t['border']};
                border-radius: 10px;
                color: {t['text_primary']};
                font-size: 14px;
                min-width: 36px;
            }}
            QPushButton#close_button:hover {{
                background: #EF4444;
                color: white;
                border-color: #EF4444;
            }}
            QPushButton#primary_button {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t['gradient_start']}, stop:1 {t['gradient_end']});
                border: none;
                border-radius: 10px;
                color: white;
                font-family: Inter;
                font-weight: bold;
                font-size: 10px;
                padding: 0 16px;
            }}
            QPushButton#primary_button:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #9F6EFF, stop:1 #F472B6);
            }}
            QPushButton#secondary_button {{
                background: {t['bg_tertiary']};
                border: 1px solid {t['border']};
                border-radius: 10px;
                color: {t['text_secondary']};
                font-family: Inter;
                font-size: 10px;
                font-weight: 500;
                padding: 0 16px;
            }}
            QPushButton#secondary_button:hover {{
                background: {t['accent']};
                color: white;
                border-color: {t['accent']};
            }}
            /* ── Paste button — blue ── */
            QPushButton#paste_button {{
                background: rgba(59, 130, 246, 0.15);
                border: 1px solid rgba(59, 130, 246, 0.4);
                border-radius: 10px;
                color: {t['accent_blue']};
                font-family: Inter;
                font-size: 10px;
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton#paste_button:hover {{
                background: {t['accent_blue']};
                color: white;
                border-color: {t['accent_blue']};
            }}
            /* ── Pause All button — amber ── */
            QPushButton#pause_button {{
                background: rgba(245, 158, 11, 0.15);
                border: 1px solid rgba(245, 158, 11, 0.4);
                border-radius: 10px;
                color: {t['accent_yellow']};
                font-family: Inter;
                font-size: 10px;
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton#pause_button:hover {{
                background: {t['accent_yellow']};
                color: white;
                border-color: {t['accent_yellow']};
            }}
            /* ── Resume All button — green ── */
            QPushButton#resume_button {{
                background: rgba(16, 185, 129, 0.15);
                border: 1px solid rgba(16, 185, 129, 0.4);
                border-radius: 10px;
                color: {t['accent_green']};
                font-family: Inter;
                font-size: 10px;
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton#resume_button:hover {{
                background: {t['accent_green']};
                color: white;
                border-color: {t['accent_green']};
            }}
            /* ── Stop All button — red ── */
            QPushButton#stop_button {{
                background: rgba(239, 68, 68, 0.15);
                border: 1px solid rgba(239, 68, 68, 0.4);
                border-radius: 10px;
                color: {t['accent_red']};
                font-family: Inter;
                font-size: 10px;
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton#stop_button:hover {{
                background: {t['accent_red']};
                color: white;
                border-color: {t['accent_red']};
            }}
            QWidget#hero {{
                background: {t['bg_secondary']};
                border-radius: 14px;
                padding: 10px;
            }}
            QTextEdit#url_input {{
                background: {t['bg_input']};
                border: 2px solid {t['border']};
                border-radius: 12px;
                color: {t['text_primary']};
                padding: 12px;
                font-family: Inter;
                font-size: 9pt;
            }}
            QTextEdit#url_input:focus {{
                border-color: {t['border_focus']};
            }}
            QLabel#section_title {{
                color: {t['text_primary']};
            }}
            QLabel#active_count {{
                color: {t['accent']};
                padding: 2px 10px;
                border-radius: 16px;
                background: {t['bg_tertiary']};
            }}
            QPushButton#ghost_button {{
                background: transparent;
                border: none;
                color: {t['text_muted']};
                padding: 6px 10px;
                border-radius: 16px;
            }}
            QPushButton#ghost_button:hover {{
                color: {t['accent']};
                background: {t['bg_hover']};
            }}
            QPushButton#failed_btn {{
                background: transparent;
                border: 1px solid #EF4444;
                color: #EF4444;
                padding: 4px 10px;
                border-radius: 12px;
                font-weight: 600;
            }}
            QPushButton#failed_btn:hover {{
                background: #EF4444;
                color: white;
            }}
            QScrollArea#downloads_scroll {{
                background: transparent;
                border: none;
            }}
            QWidget#card_container {{
                background: transparent;
            }}
            QLabel#empty_text {{
                color: {t['text_muted']};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 5px;
                border-radius: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {t['scrollbar']};
                border-radius: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t['scrollbar_hover']};
            }}
            /* Bottom bar styles */
            QWidget#bottom_bar {{
                background: transparent;
                border-top: 1px solid {t['border']};
            }}
            QFrame#divider {{
                background: {t['border']};
                max-width: 1px;
            }}
            QWidget#footer_bar {{
                background: transparent;
                border-top: 1px solid {t['border']};
            }}
            QLabel#footer_text {{
                color: {t['text_muted']};
                background: transparent;
            }}
            QLabel#footer_lic_ok {{
                color: {t['accent_green']};
                background: transparent;
            }}
            QLabel#footer_lic_warn {{
                color: {t['accent_yellow']};
                background: transparent;
            }}
            QLabel#capacity_icon {{
                color: {t['text_secondary']};
            }}
            QLabel#space_info {{
                color: {t['text_muted']};
            }}
        """)
        
        self.active_count.setStyleSheet(f"""
            color: {t['accent']};
            background: {t['bg_tertiary']};
            padding: 2px 10px;
            border-radius: 16px;
        """)
    
        # Update bottom bar
        self._update_bottom_bar_theme()
    
    def _open_settings(self):
        from widgets.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.settings_manager, self._theme, self)
        if dialog.exec() == QDialog.Accepted:
            max_concurrent = int(self.settings_manager.get("concurrent_downloads", 3))
            self.queue_manager.set_max_concurrent(max_concurrent)
            self._output_dir = self.settings_manager.get("output_dir", str(Path.home() / "Downloads"))
            self._update_capacity()
    
    def _toggle_theme(self):
        """Toggle between dark and light theme"""
        self._is_dark = not self._is_dark
        self._theme = DARK_THEME if self._is_dark else LIGHT_THEME
        
        self.theme_btn.setText("🌙" if self._is_dark else "☀️")
        
        self._apply_global_theme()
        self.format_panel.update_theme(self._theme)
        self.stats_bar.update_theme(self._theme)
        # Update all download cards
        for card in self._cards.values():
            card.update_theme(self._theme)
        # Update scraper window if open
        if self._scraper_win is not None:
            try:
                self._scraper_win.update_theme(self._theme)
            except RuntimeError:
                self._scraper_win = None
        
        # Update bottom bar capacity display
        self._update_bottom_bar_theme()
    
    def _toggle_global_pause_resume(self):
        active_tasks = [tid for tid, t in self._tasks.items() if t["status"] in ["active", "queued", "fetching"]]
        paused_tasks = [tid for tid, t in self._tasks.items() if t["status"] == "paused"]
        
        if paused_tasks:
            self.queue_manager.resume_all()
            for card in self._cards.values():
                if self._tasks.get(card.task_id, {}).get("status") == "paused":
                    card.set_resumed()
                    self._tasks[card.task_id]["status"] = "active"
            self.global_control_btn.setText("⏸ Pause All")
            self.global_control_btn.setObjectName("pause_button")
            self.global_control_btn.setStyle(self.global_control_btn.style())
            self._global_paused = False
        elif active_tasks:
            self.queue_manager.pause_all()
            for card in self._cards.values():
                if self._tasks.get(card.task_id, {}).get("status") in ["active", "queued"]:
                    card.set_paused()
                    self._tasks[card.task_id]["status"] = "paused"
            self.global_control_btn.setText("▶ Resume All")
            self.global_control_btn.setObjectName("resume_button")
            self.global_control_btn.setStyle(self.global_control_btn.style())
            self._global_paused = True
        
        self._update_stats()
    
    def _stop_all(self):
        # Cancel all in-progress fetches
        for fetch_worker in list(self._fetch_workers.values()):
            fetch_worker.cancel()
        self._fetch_workers.clear()
        self._pending_downloads.clear()

        self.queue_manager.cancel_all()
        for card in self._cards.values():
            if self._tasks.get(card.task_id, {}).get("status") in ["active", "paused", "queued", "fetching"]:
                card.set_cancelled()
                self._tasks[card.task_id]["status"] = "cancelled"
        self.global_control_btn.setText("⏸ Pause All")
        self._global_paused = False
        self._update_stats()
    
    # ────────────────────────────── Channel / Profile Scraper ──────────────
    def _on_url_input_changed(self):
        """Called whenever the URL text box changes – start debounce timer."""
        if self._ignore_url_change:
            return
        self._scrape_debounce.start()

    def _is_scraper_win_alive(self) -> bool:
        """Safely check if the scraper window C++ object is still alive and visible."""
        if self._scraper_win is None:
            return False
        try:
            return self._scraper_win.isVisible()
        except RuntimeError:
            # C++ object already deleted (WA_DeleteOnClose)
            self._scraper_win = None
            return False

    def _debounced_scrape_check(self):
        """Runs 800ms after user stops typing – opens scraper window if channel URL."""
        text = self.url_input.toPlainText().strip()
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        if not lines:
            return

        # Check all lines for channel/profile URLs (not just the first one)
        for line in lines:
            if is_channel_or_profile_url(line):
                # Don't reopen window for same URL if already open and alive
                if (self._is_scraper_win_alive() and
                        getattr(self._scraper_win, '_channel_url', '') == line):
                    return
                self._open_scraper_window(line)
                return  # Open scraper for the first channel/profile URL found

    def _open_scraper_window(self, url: str):
        """Create and show the ScraperWindow, then start the worker."""
        # Close any existing scraper window first
        self._cancel_scrape()

        # Extract profile name from the channel URL for subfolder creation
        from channel_scraper import extract_profile_name
        profile_name = extract_profile_name(url)

        win = ScraperWindow(url, self._theme, parent=self)
        win.add_to_queue.connect(
            lambda urls: self._add_scraped_to_queue(urls, profile_name)
        )
        # WA_DeleteOnClose means Qt destroys the C++ object on close;
        # connect destroyed so we null our reference immediately.
        win.destroyed.connect(self._on_scraper_win_destroyed)
        self._scraper_win = win

        # Start scraper worker
        worker = ChannelScraperWorker(url)
        worker._url_scraped = url
        worker.video_found.connect(win.add_video)
        worker.progress_update.connect(win.update_status)
        worker.scrape_finished.connect(lambda videos, err: win.scrape_done(err))
        win.set_scraper_worker(worker)
        self._scraper_worker = worker
        worker.start()

        win.show()

    def _cancel_scrape(self):
        """Cancel any in-progress scrape and close window."""
        if self._scraper_worker and self._scraper_worker.isRunning():
            self._scraper_worker.cancel()
            self._scraper_worker.quit()
            self._scraper_worker.wait(500)
        self._scraper_worker = None
        if self._scraper_win is not None:
            try:
                self._scraper_win.close()
            except RuntimeError:
                pass
            self._scraper_win = None

    def _on_scraper_win_destroyed(self):
        """Called when the ScraperWindow C++ object is destroyed (WA_DeleteOnClose)."""
        self._scraper_win = None

    def _add_scraped_to_queue(self, urls: list, profile_name: str = None):
        """Receive selected URLs from the scraper window and enqueue them."""
        if not urls:
            return

        self._ignore_url_change = True
        self.url_input.setPlainText("\n".join(urls))
        self._ignore_url_change = False

        self._start_download(profile_name=profile_name)

    # ───────────────────────────────────────────────────────────────────────
    def _paste_url(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self.url_input.setText(text)
        self.url_input.setFocus()
    
    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder", self._output_dir)
        if folder:
            self._output_dir = folder
            self.settings_manager.set("output_dir", folder)
            self._update_capacity()
    
    def _start_download(self, profile_name: str = None):
        urls_text = self.url_input.toPlainText().strip()
        if not urls_text:
            self._shake_input()
            self._show_url_hint("⚠  Please paste a URL before downloading.", "warn")
            return

        urls = [url.strip() for url in urls_text.split('\n')
                if url.strip() and (url.startswith("http://") or url.startswith("https://"))]

        if not urls:
            self._shake_input()
            self._show_url_hint("⚠  No valid URL found — make sure it starts with http:// or https://", "warn")
            return

        # ── Internet connectivity check ───────────────────────────────────────
        if not self._is_connected():
            self._shake_input()
            self._show_url_hint("✕  No internet connection — please check your network and try again.", "error")
            return
        # ─────────────────────────────────────────────────────────────────────

        self.url_input.clear()
        settings = self.format_panel.get_settings()
        auto_create = self.settings_manager.get("auto_create_subfolders", True)

        from channel_scraper import extract_profile_name

        # Process in reverse so the first URL ends up at the top of the list
        for url in reversed(urls):
            self._counter += 1
            task_id = f"task_{self._counter}_{int(time.time())}"

            # Create the card immediately — shows "Fetching information..." by default
            card = ModernDownloadCard(task_id, url, self._theme)
            card.cancel_requested.connect(self._cancel_download)
            card.pause_requested.connect(self._pause_download)
            card.resume_requested.connect(self._resume_download)
            card.open_folder.connect(self._open_folder_path)
            self._cards[task_id] = card
            self.cards_layout.insertWidget(0, card)
            self.empty_state.hide()

            effective_profile = profile_name or extract_profile_name(url)

            # Save download settings — picked up in _on_fetch_done once info arrives
            self._pending_downloads[task_id] = {
                "url":            url,
                "output_dir":     self._output_dir,
                "quality":        settings["quality"],
                "fmt":            settings["format"],
                "audio_only":     settings["audio_only"],
                "auto_create":    auto_create,
                "profile_name":   effective_profile,
                "upscale_4k":     settings.get("upscale_4k", False),
            }
            self._tasks[task_id] = {"status": "fetching", "url": url}

            # Launch FetchWorker immediately — ALL urls probe metadata in parallel,
            # completely independent of the download concurrency limit.
            fetch_worker = FetchWorker(task_id, url)
            fetch_worker.info_ready.connect(self._on_info_ready)
            fetch_worker.fetch_done.connect(self._on_fetch_done)
            self._fetch_workers[task_id] = fetch_worker
            fetch_worker.start()

        self._update_stats()

    def _on_fetch_done(self, task_id: str, is_playlist: bool, info: dict):
        """Called when FetchWorker finishes — create and queue the DownloadWorker."""
        # Clean up fetch worker
        self._fetch_workers.pop(task_id, None)

        if task_id not in self._pending_downloads:
            return  # task was cancelled before fetch completed

        if self._tasks.get(task_id, {}).get("status") == "cancelled":
            self._pending_downloads.pop(task_id, None)
            return

        p = self._pending_downloads.pop(task_id)

        worker = DownloadWorker(
            task_id, p["url"], p["output_dir"],
            quality=p["quality"],
            fmt=p["fmt"],
            audio_only=p["audio_only"],
            is_playlist=False,           # auto-detect already done by FetchWorker
            auto_create_subfolders=p["auto_create"],
            profile_name=p["profile_name"],
            upscale_4k=p["upscale_4k"],
            pre_fetched_is_playlist=is_playlist,
            pre_fetched_info=info if not is_playlist else None,
        )
        worker.info_ready.connect(self._on_info_ready)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.playlist_progress.connect(self._on_playlist_progress)
        worker.log.connect(self._on_worker_log)

        self._workers[task_id] = worker
        self._tasks[task_id] = {"status": "queued", "url": p["url"]}

        # Queue into the concurrency-limited download queue
        self.queue_manager.add_task(task_id, worker)
        self._update_stats()

    def _on_task_added(self, task_id):
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = "active"
        self._update_stats()

    def _on_queue_task_completed(self, task_id):
        pass
    
    # ── Inline hint helpers ────────────────────────────────────────────────────

    def _show_url_hint(self, message: str, kind: str = "error"):
        """Show a short message below the URL input box and auto-hide after 3 s.

        Args:
            message: Text to display.
            kind: ``"error"`` (red) | ``"warn"`` (amber) | ``"info"`` (blue).
        """
        colour_map = {
            "error": "#FF5555",
            "warn":  "#FFB86C",
            "info":  "#8BE9FD",
        }
        colour = colour_map.get(kind, "#FF5555")
        self.url_hint_label.setText(message)
        self.url_hint_label.setStyleSheet(f"color: {colour}; font-weight: 600;")
        self.url_hint_label.show()
        # Restart auto-hide timer
        self._hint_hide_timer.stop()
        self._hint_hide_timer.start()

    def _hide_url_hint(self):
        """Hide the inline hint label."""
        self.url_hint_label.hide()
        self.url_hint_label.setText("")

    @staticmethod
    def _is_connected() -> bool:
        """Return True if the machine can reach the internet (fast, non-blocking)."""
        try:
            socket.setdefaulttimeout(3)
            socket.create_connection(("8.8.8.8", 53))
            return True
        except OSError:
            return False

    # ──────────────────────────────────────────────────────────────────────────

    def _shake_input(self):
        anim = QPropertyAnimation(self.url_input, b"geometry")
        anim.setDuration(300)
        orig = self.url_input.geometry()
        anim.setKeyValueAt(0, orig)
        anim.setKeyValueAt(0.2, QRect(orig.x() - 6, orig.y(), orig.width(), orig.height()))
        anim.setKeyValueAt(0.4, QRect(orig.x() + 6, orig.y(), orig.width(), orig.height()))
        anim.setKeyValueAt(0.6, QRect(orig.x() - 3, orig.y(), orig.width(), orig.height()))
        anim.setKeyValueAt(0.8, QRect(orig.x() + 3, orig.y(), orig.width(), orig.height()))
        anim.setKeyValueAt(1, orig)
        anim.start(QAbstractAnimation.DeleteWhenStopped)
    
    def _cancel_download(self, task_id: str):
        # Cancel an in-progress fetch if the download hasn't queued yet
        fetch_worker = self._fetch_workers.pop(task_id, None)
        if fetch_worker:
            fetch_worker.cancel()
        self._pending_downloads.pop(task_id, None)

        if task_id in self._workers:
            self._workers[task_id].cancel()
        if task_id in self._cards:
            self._cards[task_id].set_cancelled()
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = "cancelled"
        self._update_stats()
    
    def _pause_download(self, task_id: str):
        if task_id in self._workers:
            self._workers[task_id].pause()
        if task_id in self._cards:
            self._cards[task_id].set_paused()
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = "paused"
        self._update_stats()
    
    def _resume_download(self, task_id: str):
        if task_id in self._workers:
            self._workers[task_id].resume()
        if task_id in self._cards:
            self._cards[task_id].set_resumed()
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = "active"
        self._update_stats()
    
    def _open_folder_path(self, path: str):
        folder = os.path.dirname(path) if os.path.isfile(path) else self._output_dir
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.run(["open", folder])
        else:
            subprocess.run(["xdg-open", folder])
    
    def _open_failed_dialog(self):
        """Open the Failed Downloads dialog listing all failed tasks."""
        failed = [
            {"url": t["url"], "error": t.get("error", "")}
            for t in self._tasks.values()
            if t["status"] == "failed"
        ]
        if not failed:
            return
        dialog = FailedDownloadsDialog(failed, self._theme, parent=self)
        dialog.redownload_requested.connect(self._redownload_failed)
        dialog.exec()

    def _redownload_failed(self, urls: list):
        """Re-queue the selected failed URLs for download."""
        if not urls:
            return
        # Reset their status so they don't linger as failed
        for task_id, task in self._tasks.items():
            if task["status"] == "failed" and task["url"] in urls:
                task["status"] = "cancelled"   # mark as cleared so _clear_finished can remove them
        self._clear_finished()                  # remove old failed cards

        # Enqueue fresh
        self._ignore_url_change = True
        self.url_input.setPlainText("\n".join(urls))
        self._ignore_url_change = False
        self._start_download()

    def _clear_finished(self):
        to_remove = [tid for tid, t in self._tasks.items() if t["status"] in ("done", "cancelled")]
        for tid in to_remove:
            if tid in self._cards:
                card = self._cards.pop(tid)
                card.deleteLater()
            self._tasks.pop(tid, None)
            self._workers.pop(tid, None)
        
        # Remove all empty space markers
        if not self._cards:
            self.empty_state.show()
        else:
            # Ensure empty state is at the bottom
            self.empty_state.hide()
        
        self._update_stats()
    
    def _on_info_ready(self, task_id: str, info: dict):
        if task_id in self._cards:
            self._cards[task_id].update_info(info)
    
    def _on_progress(self, task_id: str, pct: float, speed: str, eta: str):
        if task_id in self._cards:
            self._cards[task_id].update_progress(pct, speed, eta)
            self._update_total_speed()
    
    def _on_playlist_progress(self, task_id: str, completed: int, total: int):
        if task_id in self._cards:
            card = self._cards[task_id]
            card.update_playlist_counter(completed, total)
            pct = (completed / total) * 100 if total > 0 else 0
            card.update_progress(pct, f"{completed}/{total}", "")
            self.stats_bar.update_video_counter(completed, total)
    
    def _update_total_speed(self):
        total_speed = 0
        for worker in self._workers.values():
            if hasattr(worker, 'current_speed'):
                total_speed += worker.current_speed
        self.stats_bar.update_speed(total_speed)
    
    def _on_finished(self, task_id: str, success: bool, message: str):
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = "done" if success else "failed"
            if not success:
                self._tasks[task_id]["error"] = message
        if task_id in self._cards:
            self._cards[task_id].set_finished(success, message, self._output_dir)
        # Clean up worker reference — prevent accumulation in memory
        worker = self._workers.pop(task_id, None)
        if worker:
            worker.deleteLater()
        self._update_stats()
        
        active_tasks = sum(1 for t in self._tasks.values() if t["status"] in ["active", "queued", "fetching"])
        paused_tasks = sum(1 for t in self._tasks.values() if t["status"] == "paused")
        if active_tasks == 0 and paused_tasks == 0:
            self.global_control_btn.setText("⏸ Pause All")
            self.global_control_btn.setObjectName("pause_button")
            self.global_control_btn.setStyle(self.global_control_btn.style())
            self._global_paused = False
    
    def _on_worker_log(self, task_id: str, line: str):
        """Update download card status during post-processing phases."""
        if task_id not in self._cards:
            return
        card = self._cards[task_id]
        if "[4K Upscale]" in line:
            card.status_label.setText("⬆ Upscaling to 4K…")
            import re
            m = re.search(r"time=(\S+)", line)
            if m:
                card.speed_label.setText(f"⏱ {m.group(1)}")
        elif "[Merger]" in line or "Merging formats" in line:
            card.status_label.setText("⚙ Merging…")
            card.speed_label.setText("")
            card.eta_label.setText("")
        elif "[VideoRecoder]" in line or "Recoding video" in line:
            card.status_label.setText("⚙ Processing…")
            card.speed_label.setText("")
            card.eta_label.setText("")

    def _update_stats(self):
        total = len(self._tasks)
        done = sum(1 for t in self._tasks.values() if t["status"] == "done")
        failed = sum(1 for t in self._tasks.values() if t["status"] == "failed")
        active = sum(1 for t in self._tasks.values() if t["status"] in ["active", "queued", "fetching"])
        paused = sum(1 for t in self._tasks.values() if t["status"] == "paused")
        
        self.stats_bar.update_stats(total, done, failed)
        self.active_count.setText(f"{active} active" if active else "")

        # Show/update failed button
        if failed > 0:
            self.failed_btn.setText(f"❌ Failed ({failed})")
            self.failed_btn.setVisible(True)
        else:
            self.failed_btn.setVisible(False)
        
        if paused > 0 and active == 0:
            self.global_control_btn.setText("▶ Resume All")
            self.global_control_btn.setObjectName("resume_button")
            self.global_control_btn.setStyle(self.global_control_btn.style())
        elif active > 0:
            self.global_control_btn.setText("⏸ Pause All")
        
        if active > 0:
            self.logo_icon.start_pulse()
        else:
            self.logo_icon.stop_pulse()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()
    
    def mouseMoveEvent(self, event):
        if hasattr(self, 'drag_pos') and event.buttons() == Qt.LeftButton:
            self.move(self.pos() + event.globalPosition().toPoint() - self.drag_pos)
            self.drag_pos = event.globalPosition().toPoint()

    def closeEvent(self, event):
        """Cancel all running workers cleanly before closing."""
        self._scrape_debounce.stop()
        self._cancel_scrape()

        # Stop timers
        if hasattr(self, 'capacity_timer'):
            self.capacity_timer.stop()
        if hasattr(self, '_license_check_timer'):
            self._license_check_timer.stop()

        # Cancel every active download worker and wait for it to exit
        for worker in list(self._workers.values()):
            try:
                if worker.isRunning():
                    worker.cancel()
            except Exception:
                pass
        self._workers.clear()

        super().closeEvent(event)

    def _update_bottom_bar_theme(self):
        """Update bottom bar theme colors"""
        t = self._theme
        
        # Update stats bar
        self.stats_bar.update_theme(t)
        
        # Update capacity widget styles
        self.capacity_percent.setStyleSheet(f"color: {t['accent']}; font-weight: bold;")
        self.space_info.setStyleSheet(f"color: {t['text_muted']};")
        
        # Update capacity bar colors based on usage
        percent = float(self.capacity_percent.text().replace('%', '')) if self.capacity_percent.text() != '0%' else 0
        if percent > 90:
            self.capacity_percent.setStyleSheet("color: #EF4444; font-weight: bold;")
            self.capacity_bar.setStyleSheet("""
                QProgressBar {
                    background: rgba(128, 128, 128, 0.2);
                    border: none;
                    border-radius: 2px;
                }
                QProgressBar::chunk {
                    background: #EF4444;
                    border-radius: 2px;
                }
            """)
        elif percent > 75:
            self.capacity_percent.setStyleSheet("color: #F59E0B; font-weight: bold;")
            self.capacity_bar.setStyleSheet("""
                QProgressBar {
                    background: rgba(128, 128, 128, 0.2);
                    border: none;
                    border-radius: 2px;
                }
                QProgressBar::chunk {
                    background: #F59E0B;
                    border-radius: 2px;
                }
            """)
        else:
            self.capacity_percent.setStyleSheet(f"color: {t['accent']}; font-weight: bold;")
            self.capacity_bar.setStyleSheet(f"""
                QProgressBar {{
                    background: rgba(128, 128, 128, 0.2);
                    border: none;
                    border-radius: 2px;
                }}
                QProgressBar::chunk {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {t['gradient_start']}, stop:1 {t['gradient_end']});
                    border-radius: 2px;
                }}
            """)