"""Format selection panel widget"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QCheckBox
from PySide6.QtGui import QFont


class ModernFormatPanel(QWidget):
    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._setup_ui()
        self._apply_theme()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        # Quality selector
        quality_group = QWidget()
        quality_layout = QHBoxLayout(quality_group)
        quality_layout.setSpacing(6)
        
        quality_label = QLabel("Quality")
        quality_label.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Best", "2160p", "1440p", "1080p", "720p", "480p", "360p"])
        self.quality_combo.setFixedWidth(90)
        
        quality_layout.addWidget(quality_label)
        quality_layout.addWidget(self.quality_combo)
        
        # Format selector
        format_group = QWidget()
        format_layout = QHBoxLayout(format_group)
        format_layout.setSpacing(6)
        
        format_label = QLabel("Format")
        format_label.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP4", "MKV", "WEBM", "MP3", "M4A"])
        self.format_combo.setFixedWidth(90)
        
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_combo)

        # 4K Upscale checkbox
        self.upscale_check = QCheckBox("⬆ 4K Upscale")
        self.upscale_check.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        self.upscale_check.setToolTip(
            "Re-encode and upscale output to 3840x2160 (4K) using Lanczos filter.\n"
            "Requires ffmpeg. Slower — best for archiving or presentation on 4K displays."
        )
        # Disable upscale when audio-only is selected
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)

        layout.addWidget(quality_group)
        layout.addWidget(format_group)
        layout.addWidget(self.upscale_check)
        layout.addStretch()
    
    def _on_format_changed(self, index: int):
        """Disable 4K upscale for audio-only formats."""
        audio_only = index in (3, 4)   # MP3, M4A
        self.upscale_check.setEnabled(not audio_only)
        if audio_only:
            self.upscale_check.setChecked(False)
        
    
    
    def _apply_theme(self):
        t = self.theme
        self.setStyleSheet(f"""
            QLabel {{
                color: {t['text_secondary']};
            }}
            QComboBox {{
                background: {t['bg_input']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                color: {t['text_primary']};
                padding: 4px 6px;
                font-size: 9pt;
            }}
            QComboBox:hover {{
                border-color: {t['border_focus']};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background: {t['bg_card']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                color: {t['text_primary']};
                selection-background-color: {t['accent']};
            }}
            QCheckBox {{
                color: {t['text_secondary']};
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 2px solid {t['border']};
                background: {t['bg_input']};
            }}
            QCheckBox::indicator:checked {{
                background: {t['accent']};
                border-color: {t['accent']};
            }}
            QCheckBox:disabled {{
                color: {t['text_muted']};
            }}
        """)
    
    def get_settings(self) -> dict:
        quality_map = {0: "best", 1: "2160", 2: "1440", 3: "1080", 4: "720", 5: "480", 6: "360"}
        format_map = {0: "mp4", 1: "mkv", 2: "webm", 3: "mp3", 4: "m4a"}
        audio_only = self.format_combo.currentIndex() in (3, 4)
        return {
            "quality": quality_map.get(self.quality_combo.currentIndex(), "best"),
            "format": format_map.get(self.format_combo.currentIndex(), "mp4"),
            "audio_only": audio_only,
            "upscale_4k": self.upscale_check.isChecked() and not audio_only,
        }
        
        
    
    def update_theme(self, t: dict):
        self.theme = t
        self._apply_theme()