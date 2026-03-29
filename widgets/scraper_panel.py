"""Scraper panel – shown when user inputs a channel / profile URL"""

from typing import List, Dict, Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QCheckBox, QProgressBar
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class VideoResultRow(QWidget):
    """A single row in the scrape results list."""

    def __init__(self, video: Dict, theme: dict, parent=None):
        super().__init__(parent)
        self.video = video
        self._theme = theme
        self.setObjectName("video_row")
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Checkbox
        self.check = QCheckBox()
        self.check.setChecked(True)
        self.check.setFixedSize(20, 20)
        layout.addWidget(self.check)

        # Info column
        info = QVBoxLayout()
        info.setSpacing(2)

        title = self.video.get("title", "Untitled")
        title_lbl = QLabel(title[:72] + "…" if len(title) > 72 else title)
        title_lbl.setObjectName("row_title")
        title_lbl.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        title_lbl.setWordWrap(False)
        info.addWidget(title_lbl)

        meta_parts = []
        if self.video.get("uploader"):
            meta_parts.append(self.video["uploader"])
        if self.video.get("duration"):
            meta_parts.append(self.video["duration"])
        if self.video.get("view_count"):
            vc = self.video["view_count"]
            if vc >= 1_000_000:
                meta_parts.append(f"{vc/1_000_000:.1f}M views")
            elif vc >= 1_000:
                meta_parts.append(f"{vc//1_000}K views")
            else:
                meta_parts.append(f"{vc} views")

        meta_lbl = QLabel("  ·  ".join(meta_parts))
        meta_lbl.setObjectName("row_meta")
        meta_lbl.setFont(QFont("Inter", 8))
        info.addWidget(meta_lbl)

        layout.addLayout(info, 1)

        self._apply_theme()

    def _apply_theme(self):
        t = self._theme
        self.setStyleSheet(f"""
            QWidget#video_row {{
                background: {t['bg_tertiary']};
                border-radius: 8px;
                border: 1px solid {t['border']};
            }}
            QWidget#video_row:hover {{
                background: {t['bg_hover']};
                border-color: {t['accent']};
            }}
            QLabel#row_title {{ color: {t['text_primary']}; }}
            QLabel#row_meta  {{ color: {t['text_muted']}; }}
            QCheckBox {{
                color: {t['text_primary']};
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 2px solid {t['border']};
                background: {t['bg_input']};
            }}
            QCheckBox::indicator:checked {{
                background: {t['accent']};
                border-color: {t['accent']};
            }}
        """)

    def update_theme(self, theme: dict):
        self._theme = theme
        self._apply_theme()

    def is_selected(self) -> bool:
        return self.check.isChecked()


class ScraperPanel(QWidget):
    """
    Panel that appears below the URL input when a channel/profile URL is detected.
    Displays scrape progress, lists found videos, and provides 'Add to Queue' button.
    """

    # Emitted when user clicks "Add to Queue" with selected video URLs
    add_to_queue = Signal(list)   # list of url strings

    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._rows: List[VideoResultRow] = []
        self._total_found = 0
        self.setObjectName("scraper_panel")
        self._build()
        self.hide()

    # ------------------------------------------------------------------ build
    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # ── Header row ──────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(8)

        icon_lbl = QLabel("🔍")
        icon_lbl.setFont(QFont("Segoe UI", 12))
        header.addWidget(icon_lbl)

        self.status_lbl = QLabel("Scanning channel…")
        self.status_lbl.setObjectName("scraper_status")
        self.status_lbl.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        header.addWidget(self.status_lbl, 1)

        self.cancel_btn = QPushButton("✕ Cancel")
        self.cancel_btn.setObjectName("scraper_cancel_btn")
        self.cancel_btn.setFixedHeight(28)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        header.addWidget(self.cancel_btn)

        layout.addLayout(header)

        # ── Progress bar ─────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("scraper_progress")
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 0)   # indeterminate
        layout.addWidget(self.progress_bar)

        # ── Select-all row ───────────────────────────────────────────────────
        self.select_row = QWidget()
        sel_layout = QHBoxLayout(self.select_row)
        sel_layout.setContentsMargins(0, 0, 0, 0)
        sel_layout.setSpacing(8)

        self.select_all_check = QCheckBox("Select All")
        self.select_all_check.setChecked(True)
        self.select_all_check.setFont(QFont("Inter", 9))
        self.select_all_check.stateChanged.connect(self._toggle_select_all)
        sel_layout.addWidget(self.select_all_check)

        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("scraper_count")
        self.count_lbl.setFont(QFont("Inter", 8))
        sel_layout.addWidget(self.count_lbl)

        sel_layout.addStretch()

        self.add_btn = QPushButton("➕ Add to Queue")
        self.add_btn.setObjectName("scraper_add_btn")
        self.add_btn.setFixedHeight(32)
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self._on_add_clicked)
        self.add_btn.hide()
        sel_layout.addWidget(self.add_btn)

        self.select_row.hide()
        layout.addWidget(self.select_row)

        # ── Scrollable video list ────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setObjectName("scraper_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(260)

        self.list_widget = QWidget()
        self.list_widget.setObjectName("scraper_list")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()

        scroll.setWidget(self.list_widget)
        layout.addWidget(scroll)

        self._apply_theme()

    # ─────────────────────────────────────────────────── public interface
    def start_scrape(self):
        """Reset and show the panel in 'loading' state."""
        self._rows.clear()
        self._total_found = 0
        # Remove all rows from layout (keep the stretch at index 0)
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        self.progress_bar.setRange(0, 0)
        self.status_lbl.setText("Connecting to channel…")
        self.cancel_btn.show()
        self.add_btn.hide()
        self.select_row.hide()
        self.count_lbl.setText("")
        self.show()

    def add_video(self, video: dict):
        """Append a newly-scraped video row."""
        row = VideoResultRow(video, self._theme)
        row.check.stateChanged.connect(self._update_count_label)
        self._rows.append(row)
        # Insert before the stretch (index 0)
        self.list_layout.insertWidget(self.list_layout.count() - 1, row)
        self._total_found += 1
        self._update_count_label()

    def scrape_done(self, error: str = ""):
        """Called when scraping finishes."""
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)

        if error and not self._rows:
            self.status_lbl.setText(f"⚠ {error}")
            self.cancel_btn.hide()
            return

        n = self._total_found
        self.status_lbl.setText(f"Found {n} video{'s' if n != 1 else ''}")
        self.cancel_btn.hide()

        if n > 0:
            self.select_row.show()
            self.add_btn.show()
            self._update_count_label()

    def update_status(self, text: str):
        self.status_lbl.setText(text)

    def reset(self):
        """Hide the panel and clear everything."""
        self.hide()
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()
        self._total_found = 0

    def update_theme(self, theme: dict):
        self._theme = theme
        for row in self._rows:
            row.update_theme(theme)
        self._apply_theme()

    # ───────────────────────────────────────────────────────── private
    def _toggle_select_all(self, state):
        checked = state == Qt.Checked
        for row in self._rows:
            row.check.blockSignals(True)
            row.check.setChecked(checked)
            row.check.blockSignals(False)
        self._update_count_label()

    def _update_count_label(self):
        selected = sum(1 for r in self._rows if r.is_selected())
        total = len(self._rows)
        self.count_lbl.setText(f"{selected} / {total} selected")

        # Keep select-all checkbox in sync without triggering its signal
        self.select_all_check.blockSignals(True)
        if selected == 0:
            self.select_all_check.setCheckState(Qt.Unchecked)
        elif selected == total:
            self.select_all_check.setCheckState(Qt.Checked)
        else:
            self.select_all_check.setCheckState(Qt.PartiallyChecked)
        self.select_all_check.blockSignals(False)

    def _on_add_clicked(self):
        urls = [r.video["url"] for r in self._rows if r.is_selected()]
        if urls:
            self.add_to_queue.emit(urls)
            # Provide visual feedback
            self.add_btn.setText(f"✅ {len(urls)} Added!")
            self.add_btn.setEnabled(False)

    def _apply_theme(self):
        t = self._theme
        self.setStyleSheet(f"""
            QWidget#scraper_panel {{
                background: {t['bg_secondary']};
                border-radius: 12px;
                padding: 8px;
            }}
            QLabel#scraper_status {{
                color: {t['text_primary']};
            }}
            QLabel#scraper_count {{
                color: {t['text_muted']};
            }}
            QPushButton#scraper_cancel_btn {{
                background: {t['bg_tertiary']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                color: {t['text_secondary']};
                font-size: 9px;
                padding: 0 10px;
            }}
            QPushButton#scraper_cancel_btn:hover {{
                background: #EF4444;
                color: white;
                border-color: #EF4444;
            }}
            QPushButton#scraper_add_btn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t['gradient_start']}, stop:1 {t['gradient_end']});
                border: none;
                border-radius: 10px;
                color: white;
                font-weight: bold;
                font-size: 10px;
                padding: 0 16px;
            }}
            QPushButton#scraper_add_btn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #9F6EFF, stop:1 #F472B6);
            }}
            QPushButton#scraper_add_btn:disabled {{
                background: {t['bg_tertiary']};
                color: {t['text_muted']};
            }}
            QProgressBar#scraper_progress {{
                background: {t['bg_tertiary']};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar#scraper_progress::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t['gradient_start']}, stop:1 {t['gradient_end']});
                border-radius: 2px;
            }}
            QScrollArea#scraper_scroll {{
                background: transparent;
                border: none;
            }}
            QWidget#scraper_list {{
                background: transparent;
            }}
            QCheckBox {{
                color: {t['text_primary']};
                font-size: 9px;
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
            QCheckBox::indicator:indeterminate {{
                background: {t['accent']};
                border-color: {t['accent']};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {t['scrollbar']};
                border-radius: 2px;
            }}
        """)
