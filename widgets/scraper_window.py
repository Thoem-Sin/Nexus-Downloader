"""Scraper Window – a floating popup that shows channel scrape results."""

from typing import List, Dict
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QCheckBox, QProgressBar, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QFont, QColor


# ─────────────────────────────────────────── Video Row ──────────────────────

class VideoResultRow(QWidget):
    def __init__(self, video: Dict, theme: dict, parent=None):
        super().__init__(parent)
        self.video = video
        self._theme = theme
        self.setObjectName("video_row")
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)

        self.check = QCheckBox()
        self.check.setChecked(True)
        layout.addWidget(self.check)

        info = QVBoxLayout()
        info.setSpacing(2)

        title = self.video.get("title", "Untitled")
        title_lbl = QLabel(title[:80] + "…" if len(title) > 80 else title)
        title_lbl.setObjectName("row_title")
        title_lbl.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        info.addWidget(title_lbl)

        meta_parts = []
        if self.video.get("uploader"):
            meta_parts.append(self.video["uploader"])
        if self.video.get("duration"):
            meta_parts.append(self.video["duration"])
        vc = self.video.get("view_count", 0)
        if vc:
            if vc >= 1_000_000:
                meta_parts.append(f"{vc/1_000_000:.1f}M views")
            elif vc >= 1_000:
                meta_parts.append(f"{vc//1_000}K views")

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
            QCheckBox::indicator {{
                width: 16px; height: 16px;
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


# ─────────────────────────────────────────── Scraper Window ─────────────────

class ScraperWindow(QDialog):
    """
    Standalone popup window for browsing and selecting videos from a
    scraped channel / profile. Emits add_to_queue(urls) when user confirms.
    """

    add_to_queue = Signal(list)   # list[str] of video URLs

    def __init__(self, channel_url: str, theme: dict, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setModal(False)   # non-blocking – main window stays interactive

        self._theme = theme
        self._rows: List[VideoResultRow] = []
        self._channel_url = channel_url
        self._scraper_worker = None
        self._drag_pos = None

        self.setMinimumSize(620, 500)
        self.resize(680, 620)

        self._build()
        self._apply_theme()
        self._center_on_parent(parent)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 8)
        self.main_container.setGraphicsEffect(shadow)

    # ──────────────────────────────────── Layout ─────────────────────────────

    def _build(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(0)

        self.main_container = QWidget()
        self.main_container.setObjectName("scraper_win_container")
        container_layout = QVBoxLayout(self.main_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Title bar
        container_layout.addWidget(self._build_titlebar())

        # Body
        body = QWidget()
        body.setObjectName("scraper_win_body")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 10, 12, 10)
        body_layout.setSpacing(8)

        # Status + progress
        self.status_lbl = QLabel("Connecting to channel…")
        self.status_lbl.setObjectName("sw_status")
        self.status_lbl.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        body_layout.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("sw_progress")
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 0)
        body_layout.addWidget(self.progress_bar)

        # Toolbar: select-all + count + add button
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.select_all_check = QCheckBox("Select All")
        self.select_all_check.setChecked(True)
        self.select_all_check.setTristate(True)  # allows indeterminate display
        self.select_all_check.setFont(QFont("Inter", 9))
        # Use clicked (user action only) not stateChanged (avoids feedback loops)
        self.select_all_check.clicked.connect(self._toggle_select_all)
        toolbar.addWidget(self.select_all_check)

        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("sw_count")
        self.count_lbl.setFont(QFont("Inter", 8))
        toolbar.addWidget(self.count_lbl)

        toolbar.addStretch()

        self.add_btn = QPushButton("➕  Add Selected to Queue")
        self.add_btn.setObjectName("sw_add_btn")
        self.add_btn.setFixedHeight(36)
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self._on_add_clicked)
        self.add_btn.setEnabled(False)
        toolbar.addWidget(self.add_btn)

        self.toolbar_widget = QWidget()
        self.toolbar_widget.setLayout(toolbar)
        body_layout.addWidget(self.toolbar_widget)

        # Separator
        sep = QFrame()
        sep.setObjectName("sw_sep")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        body_layout.addWidget(sep)

        # Scrollable video list
        scroll = QScrollArea()
        scroll.setObjectName("sw_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.list_widget = QWidget()
        self.list_widget.setObjectName("sw_list")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(5)
        self.list_layout.addStretch()

        # Empty state
        self.empty_lbl = QLabel("Scanning channel for videos…")
        self.empty_lbl.setObjectName("sw_empty")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setFont(QFont("Inter", 9))
        self.list_layout.insertWidget(0, self.empty_lbl)

        scroll.setWidget(self.list_widget)
        body_layout.addWidget(scroll, 1)

        container_layout.addWidget(body)
        root_layout.addWidget(self.main_container)

    def _build_titlebar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("sw_titlebar")
        bar.setFixedHeight(52)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 10, 0)
        layout.setSpacing(8)

        icon = QLabel("🔍")
        icon.setFont(QFont("Segoe UI", 14))
        layout.addWidget(icon)

        self.title_lbl = QLabel("Channel Scraper")
        self.title_lbl.setObjectName("sw_title")
        self.title_lbl.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        layout.addWidget(self.title_lbl, 1)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("dialog_close_btn")
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self._on_close)
        layout.addWidget(self.close_btn)

        return bar

    # ──────────────────────────────────── Public API ─────────────────────────

    def add_video(self, video: dict):
        """Called by scraper worker for each found video."""
        if hasattr(self, 'empty_lbl') and self.empty_lbl.isVisible():
            self.empty_lbl.hide()

        row = VideoResultRow(video, self._theme)
        row.check.stateChanged.connect(self._update_count)
        self._rows.append(row)
        self.list_layout.insertWidget(self.list_layout.count() - 1, row)
        self._update_count()

    def update_status(self, text: str):
        self.status_lbl.setText(text)

    def scrape_done(self, error: str = ""):
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)

        n = len(self._rows)
        if error and n == 0:
            self.status_lbl.setText(f"⚠  {error}")
            return

        self.status_lbl.setText(f"✅  Found {n} video{'s' if n != 1 else ''} — select and add to queue")
        if n > 0:
            self.add_btn.setEnabled(True)
            self._update_count()

    def update_theme(self, theme: dict):
        self._theme = theme
        for row in self._rows:
            row.update_theme(theme)
        self._apply_theme()

    def set_scraper_worker(self, worker):
        self._scraper_worker = worker

    # ──────────────────────────────────── Private ────────────────────────────

    def _on_close(self):
        if self._scraper_worker and self._scraper_worker.isRunning():
            self._scraper_worker.cancel()
            self._scraper_worker.quit()
            self._scraper_worker.wait(500)
        self.reject()

    def _on_add_clicked(self):
        urls = [r.video["url"] for r in self._rows if r.is_selected()]
        if not urls:
            return
        self.add_to_queue.emit(urls)
        self.add_btn.setText(f"✅  {len(urls)} video{'s' if len(urls)!=1 else ''} added!")
        self.add_btn.setEnabled(False)
        # Auto-close after short delay
        QTimer.singleShot(900, self.accept)

    def _toggle_select_all(self, checked: bool):
        """User clicked the Select All checkbox. checked = new Qt checked state.
        With tristate the cycle is: Unchecked → PartiallyChecked → Checked.
        We treat both Checked AND PartiallyChecked (from an indeterminate click)
        as 'select all', and only Unchecked as 'deselect all'."""
        # Force it to a clean binary state immediately so the checkbox
        # never stays in PartiallyChecked after a user click.
        current = self.select_all_check.checkState()
        want_all = (current != Qt.Unchecked)   # PartiallyChecked or Checked → select all

        self.select_all_check.blockSignals(True)
        self.select_all_check.setCheckState(Qt.Checked if want_all else Qt.Unchecked)
        self.select_all_check.blockSignals(False)

        for row in self._rows:
            row.check.blockSignals(True)
            row.check.setChecked(want_all)
            row.check.blockSignals(False)
        self._update_count()

    def _update_count(self):
        selected = sum(1 for r in self._rows if r.is_selected())
        total = len(self._rows)
        self.count_lbl.setText(f"{selected} / {total} selected")

        self.select_all_check.blockSignals(True)
        if selected == 0:
            self.select_all_check.setCheckState(Qt.Unchecked)
        elif selected == total:
            self.select_all_check.setCheckState(Qt.Checked)
        else:
            self.select_all_check.setCheckState(Qt.PartiallyChecked)
        self.select_all_check.blockSignals(False)

        self.add_btn.setEnabled(selected > 0)

    def _center_on_parent(self, parent):
        if parent:
            pg = parent.geometry()
            sg = self.geometry()
            x = pg.x() + (pg.width() - sg.width()) // 2
            y = pg.y() + (pg.height() - sg.height()) // 2
            self.move(x, y)

    # ──────────────────── Draggable frameless window ─────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(self.pos() + event.globalPosition().toPoint() - self._drag_pos)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ──────────────────────────────────── Theme ──────────────────────────────

    def _apply_theme(self):
        t = self._theme
        self.setStyleSheet(f"""
            QWidget#scraper_win_container {{
                background: {t['bg_card']};
                border-radius: 18px;
                border: 1px solid {t['border']};
            }}
            QWidget#sw_titlebar {{
                background: {t['bg_secondary']};
                border-radius: 18px 18px 0 0;
                border-bottom: 1px solid {t['border']};
            }}
            QLabel#sw_title {{ color: {t['text_primary']}; }}
            QLabel#sw_status {{ color: {t['text_secondary']}; }}
            QLabel#sw_count  {{ color: {t['text_muted']}; }}
            QLabel#sw_empty  {{ color: {t['text_muted']}; padding: 40px; }}
            QPushButton#dialog_close_btn {{
                background: {t['bg_tertiary']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                color: {t['text_primary']};
                font-size: 12px;
            }}
            QPushButton#dialog_close_btn:hover {{
                background: #EF4444;
                color: white;
                border-color: #EF4444;
            }}
            QPushButton#sw_add_btn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t['gradient_start']}, stop:1 {t['gradient_end']});
                border: none;
                border-radius: 10px;
                color: white;
                font-weight: bold;
                font-size: 10px;
                padding: 0 18px;
            }}
            QPushButton#sw_add_btn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #9F6EFF, stop:1 #F472B6);
            }}
            QPushButton#sw_add_btn:disabled {{
                background: {t['bg_tertiary']};
                color: {t['text_muted']};
            }}
            QProgressBar#sw_progress {{
                background: {t['bg_tertiary']};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar#sw_progress::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t['gradient_start']}, stop:1 {t['gradient_end']});
                border-radius: 2px;
            }}
            QFrame#sw_sep {{ background: {t['border']}; }}
            QScrollArea#sw_scroll {{
                background: transparent; border: none;
            }}
            QWidget#sw_list {{ background: transparent; }}
            QWidget#sw_body {{ background: transparent; }}
            QCheckBox {{ color: {t['text_primary']}; font-size: 9px; }}
            QCheckBox::indicator {{
                width: 15px; height: 15px;
                border-radius: 4px;
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
                background: transparent; width: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {t['scrollbar']}; border-radius: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t['scrollbar_hover']};
            }}
        """)
