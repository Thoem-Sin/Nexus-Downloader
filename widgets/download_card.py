"""Modern download card widget"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from widgets.animated_components import GlassCard, GradientProgressBar


class ModernDownloadCard(GlassCard):
    cancel_requested = Signal(str)
    pause_requested = Signal(str)
    resume_requested = Signal(str)
    open_folder = Signal(str)
    
    def __init__(self, task_id: str, url: str, theme: dict, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.url = url
        self.theme = theme
        self.output_path = ""
        self.is_playlist = False
        self.playlist_completed = 0
        self.playlist_total = 0
        self.channel_name = ""
        self._setup_ui()
        self._apply_theme()
        
    def _setup_ui(self):
        self.setFixedHeight(110)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        
        # Left - Thumbnail placeholder with icon only (no image loading)
        self.thumb_widget = QLabel()
        self.thumb_widget.setFixedSize(64, 64)
        self.thumb_widget.setAlignment(Qt.AlignCenter)
        self.thumb_widget.setStyleSheet("""
            QLabel {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 8px;
            }
        """)
        self.thumb_widget.setText("🎬")
        self.thumb_widget.setFont(QFont("Segoe UI", 24))
        layout.addWidget(self.thumb_widget)
        
        # Center - Info
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setSpacing(3)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        # Title row - visitable
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        
        self.title_label = QLabel("Fetching information...")
        self.title_label.setFont(QFont("Inter", 10, QFont.Weight.Medium))
        self.title_label.setWordWrap(True)
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.title_label.setCursor(Qt.IBeamCursor)
        title_row.addWidget(self.title_label, 1)
        
        self.platform_badge = QLabel("")
        self.platform_badge.setFont(QFont("Inter", 8))
        self.platform_badge.setFixedHeight(20)
        self.platform_badge.setAlignment(Qt.AlignCenter)
        self.platform_badge.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.platform_badge.setCursor(Qt.IBeamCursor)
        title_row.addWidget(self.platform_badge)
        
        info_layout.addLayout(title_row)
        
        # URL at the top (right after title)
        url_short = self.url[:60] + "..." if len(self.url) > 60 else self.url
        self.url_label = QLabel(url_short)
        self.url_label.setFont(QFont("Inter", 7))
        self.url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.url_label.setCursor(Qt.IBeamCursor)
        self.url_label.setWordWrap(True)
        info_layout.addWidget(self.url_label)
        
        # Channel name for playlists
        self.channel_label = QLabel("")
        self.channel_label.setFont(QFont("Inter", 7))
        self.channel_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.channel_label.setCursor(Qt.IBeamCursor)
        self.channel_label.setVisible(False)
        info_layout.addWidget(self.channel_label)
        
        # Progress section
        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)
        
        self.progress_bar = GradientProgressBar()
        progress_row.addWidget(self.progress_bar, 1)
        
        self.percent_label = QLabel("0%")
        self.percent_label.setFont(QFont("Inter", 8, QFont.Weight.Medium))
        self.percent_label.setFixedWidth(45)
        self.percent_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.percent_label.setCursor(Qt.IBeamCursor)
        progress_row.addWidget(self.percent_label)
        info_layout.addLayout(progress_row)
        
        # Status row - visitable
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        
        self.status_dot = QLabel("●")
        self.status_dot.setFont(QFont("Inter", 8))
        self.status_dot.setFixedWidth(12)
        self.status_dot.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.status_dot.setCursor(Qt.IBeamCursor)
        status_row.addWidget(self.status_dot)
        
        self.status_label = QLabel("Initializing...")
        self.status_label.setFont(QFont("Inter", 8))
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.status_label.setCursor(Qt.IBeamCursor)
        status_row.addWidget(self.status_label)
        
        status_row.addStretch()
        
        self.speed_label = QLabel("")
        self.speed_label.setFont(QFont("Inter", 7))
        self.speed_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.speed_label.setCursor(Qt.IBeamCursor)
        status_row.addWidget(self.speed_label)
        
        self.eta_label = QLabel("")
        self.eta_label.setFont(QFont("Inter", 7))
        self.eta_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.eta_label.setCursor(Qt.IBeamCursor)
        status_row.addWidget(self.eta_label)
        
        info_layout.addLayout(status_row)
        
        layout.addWidget(info_widget, 1)
        
        # Right - Actions
        actions_widget = QWidget()
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setSpacing(6)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        
        self.pause_btn = QPushButton("⏸")
        self.pause_btn.setFixedSize(28, 28)
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.clicked.connect(lambda: self.pause_requested.emit(self.task_id))
        
        self.resume_btn = QPushButton("▶")
        self.resume_btn.setFixedSize(28, 28)
        self.resume_btn.setCursor(Qt.PointingHandCursor)
        self.resume_btn.setVisible(False)
        self.resume_btn.clicked.connect(lambda: self.resume_requested.emit(self.task_id))
        
        self.cancel_btn = QPushButton("✕")
        self.cancel_btn.setFixedSize(28, 28)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.task_id))
        
        self.folder_btn = QPushButton("📁")
        self.folder_btn.setFixedSize(28, 28)
        self.folder_btn.setCursor(Qt.PointingHandCursor)
        self.folder_btn.setEnabled(False)
        self.folder_btn.clicked.connect(lambda: self.open_folder.emit(self.output_path))
        
        actions_layout.addWidget(self.pause_btn)
        actions_layout.addWidget(self.resume_btn)
        actions_layout.addWidget(self.cancel_btn)
        actions_layout.addWidget(self.folder_btn)
        
        layout.addWidget(actions_widget)
    
    def _apply_theme(self):
        t = self.theme
        self.setStyleSheet(f"""
            ModernDownloadCard {{
                background: {t['bg_card']};
                border: 1px solid {t['border']};
                border-radius: 12px;
            }}
            QLabel {{
                background: transparent;
            }}
            QPushButton {{
                background: {t['bg_tertiary']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                color: {t['text_secondary']};
                font-size: 10px;
            }}
            QPushButton:hover {{
                background: {t['bg_hover']};
                color: {t['text_primary']};
            }}
            QPushButton:disabled {{
                opacity: 0.5;
            }}
        """)
        
        self.title_label.setStyleSheet(f"color: {t['text_primary']}; background: transparent;")
        self.url_label.setStyleSheet(f"color: {t['text_muted']}; background: transparent;")
        self.status_label.setStyleSheet(f"color: {t['text_secondary']}; background: transparent;")
        self.speed_label.setStyleSheet(f"color: {t['accent']}; background: transparent;")
        self.eta_label.setStyleSheet(f"color: {t['accent_secondary']}; background: transparent;")
        self.percent_label.setStyleSheet(f"color: {t['accent']}; background: transparent;")
        self.channel_label.setStyleSheet(f"color: {t['text_muted']}; background: transparent;")
        self.platform_badge.setStyleSheet(f"""
            color: {t['accent']};
            background: {t['bg_tertiary']};
            padding: 2px 8px;
            border-radius: 10px;
        """)
    
    def update_info(self, info: dict):
        title = info.get("title", "Unknown")
        self.is_playlist = info.get("is_playlist", False)
        self.channel_name = info.get("channel", info.get("uploader", ""))
        
        # Update thumbnail icon based on platform
        platform = info.get("platform", "").lower()
        platform_icons = {
            "youtube": "▶️", "vimeo": "📹", "twitter": "🐦", 
            "tiktok": "🎵", "instagram": "📸"
        }
        icon = platform_icons.get(platform, "🎬")
        self.thumb_widget.setText(icon)
        
        if self.is_playlist:
            playlist_count = info.get("playlist_count", 0)
            self.playlist_total = playlist_count
            if self.channel_name:
                self.channel_label.setText(f"📺 {self.channel_name}")
                self.channel_label.setVisible(True)
            title = f"📁 {title}"
            self.status_label.setText(f"Playlist • {playlist_count} videos")
            self.status_dot.setStyleSheet(f"color: {self.theme['accent_blue']};")
        elif len(title) > 40:
            title = title[:37] + "..."
            self.channel_label.setVisible(False)
        
        self.title_label.setText(title)
        self.platform_badge.setText(f"{icon} {platform.title() if platform else 'Video'}")
    
    def update_playlist_counter(self, completed: int, total: int):
        """Update playlist video counter - only for actual playlists"""
        if total > 1:  # Only show if it's actually a playlist (more than 1 video)
            self.playlist_completed = completed
            self.playlist_total = total
            self.status_label.setText(f"Downloading • {completed}/{total} videos")
            self.status_dot.setStyleSheet(f"color: {self.theme['accent']};")
        else:
            # Reset playlist indicators for single videos
            self.playlist_completed = 0
            self.playlist_total = 0
            self.is_playlist = False
            self.status_label.setText("Downloading")
            self.status_dot.setStyleSheet(f"color: {self.theme['accent']};")
    
    def update_progress(self, pct: float, speed: str, eta: str):
        self.progress_bar.setValue(pct)
        if pct < 100:
            self.percent_label.setText(f"{pct:.0f}%")
        else:
            self.percent_label.setText("100%")
            
        if speed and not speed.startswith("/"):
            self.speed_label.setText(f"↓ {speed}")
        if eta:
            self.eta_label.setText(f"ETA {eta}")
        
        if not self.is_playlist:
            self.status_label.setText("Downloading")
            self.status_dot.setStyleSheet(f"color: {self.theme['accent']};")
    
    def set_finished(self, success: bool, message: str, output_path: str = ""):
        self.output_path = output_path
        self.progress_bar.setValue(100 if success else 0)
        self.percent_label.setText("100%" if success else "0%")
        self.cancel_btn.setEnabled(False)
        self.folder_btn.setEnabled(success)
        self.speed_label.setText("")
        self.eta_label.setText("")
        
        if success:
            if self.is_playlist and self.playlist_total > 0:
                self.status_label.setText(f"Completed • {self.playlist_completed}/{self.playlist_total} videos")
            else:
                self.status_label.setText("Completed")
            self.status_dot.setStyleSheet(f"color: {self.theme['accent_green']};")
            self.progress_bar.setValue(100)
        else:
            self.status_label.setText("Failed")
            self.status_dot.setStyleSheet(f"color: {self.theme['accent_red']};")
    
    def set_cancelled(self):
        self.status_label.setText("Cancelled")
        self.status_dot.setStyleSheet(f"color: {self.theme['accent_yellow']};")
        self.speed_label.setText("")
        self.eta_label.setText("")
        self.pause_btn.setVisible(False)
        self.resume_btn.setVisible(False)
        self.cancel_btn.setEnabled(False)
    
    def set_paused(self):
        self.pause_btn.setVisible(False)
        self.resume_btn.setVisible(True)
        self.status_label.setText("Paused")
        self.status_dot.setStyleSheet(f"color: {self.theme['accent_yellow']};")
    
    def set_resumed(self):
        self.pause_btn.setVisible(True)
        self.resume_btn.setVisible(False)
        if self.is_playlist and self.playlist_total > 0:
            self.status_label.setText(f"Downloading • {self.playlist_completed}/{self.playlist_total} videos")
        else:
            self.status_label.setText("Downloading")
        self.status_dot.setStyleSheet(f"color: {self.theme['accent']};")
    
    def update_theme(self, theme: dict):
        self.theme = theme
        self._apply_theme()