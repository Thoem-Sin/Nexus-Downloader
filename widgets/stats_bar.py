"""Stats bar widget — inline number + text, no icons"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class ModernStatsBar(QWidget):
    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.stats = {}        # key → count QLabel
        self.stat_labels = {}  # key → name QLabel

        items = [
            ("total",     "Total"),
            ("completed", "Completed"),
            ("failed",    "Failed"),
        ]

        for i, (key, name) in enumerate(items):
            count_lbl = QLabel("0")
            count_lbl.setObjectName(f"stat_count_{key}")
            count_lbl.setFont(QFont("Inter", 10, QFont.Weight.Bold))
            count_lbl.setAlignment(Qt.AlignVCenter)

            name_lbl = QLabel(name)
            name_lbl.setObjectName("stat_name")
            name_lbl.setFont(QFont("Inter", 10))
            name_lbl.setAlignment(Qt.AlignVCenter)

            layout.addWidget(count_lbl)
            layout.addWidget(name_lbl)

            self.stats[key]       = count_lbl
            self.stat_labels[key] = name_lbl

            # Thin divider between groups (not after last)
            if i < len(items) - 1:
                div = QFrame()
                div.setFrameShape(QFrame.VLine)
                div.setFixedWidth(1)
                div.setFixedHeight(14)
                div.setObjectName("stat_divider")
                layout.addSpacing(6)
                layout.addWidget(div)
                layout.addSpacing(6)

        layout.addSpacing(8)

        # Video counter (channel / playlist mode)
        self.video_counter = QLabel("")
        self.video_counter.setObjectName("stat_video_counter")
        self.video_counter.setFont(QFont("Inter", 9))
        self.video_counter.setAlignment(Qt.AlignVCenter)
        layout.addWidget(self.video_counter)

        layout.addStretch()

        # Speed indicator
        self.speed_indicator = QLabel("0 Mbps")
        self.speed_indicator.setObjectName("stat_speed")
        self.speed_indicator.setFont(QFont("Inter", 10))
        self.speed_indicator.setAlignment(Qt.AlignVCenter)
        layout.addWidget(self.speed_indicator)

    # ── Theme ─────────────────────────────────────────────────────────────

    def _apply_theme(self):
        t = self.theme

        self.stats["total"].setStyleSheet(
            f"color: {t['text_primary']}; background: transparent;")
        self.stats["completed"].setStyleSheet(
            f"color: {t['accent_green']}; background: transparent;")
        self.stats["failed"].setStyleSheet(
            f"color: {t['accent_red']}; background: transparent;")

        for lbl in self.stat_labels.values():
            lbl.setStyleSheet(
                f"color: {t['text_muted']}; background: transparent;")

        self.setStyleSheet(f"""
            QFrame#stat_divider {{
                background: {t['border']};
                max-width: 1px;
            }}
            QLabel#stat_video_counter {{
                color: {t['text_secondary']};
                background: transparent;
            }}
            QLabel#stat_speed {{
                color: {t['accent']};
                background: transparent;
            }}
        """)

    def update_theme(self, theme: dict):
        self.theme = theme
        self._apply_theme()

    # ── Data updates ──────────────────────────────────────────────────────

    def update_stats(self, total: int, done: int, failed: int):
        self.stats["total"].setText(str(total))
        self.stats["completed"].setText(str(done))
        self.stats["failed"].setText(str(failed))

    def update_video_counter(self, completed: int, total: int):
        if total > 0:
            self.video_counter.setText(f"{completed}/{total} videos")
        else:
            self.video_counter.setText("")

    def update_speed(self, speed_mbps: float):
        self.speed_indicator.setText(f"{speed_mbps:.1f} Mbps")
