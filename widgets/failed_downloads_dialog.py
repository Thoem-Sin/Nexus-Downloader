"""Failed Downloads Dialog – lists failed URLs with retry capability."""

from typing import List, Dict
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QCheckBox, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor


# ─────────────────────────────────────── Failed URL Row ─────────────────────

class FailedUrlRow(QWidget):
    def __init__(self, url: str, error: str, theme: dict, parent=None):
        super().__init__(parent)
        self.url = url
        self.error = error
        self._theme = theme
        self.setObjectName("failed_row")
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        self.check = QCheckBox()
        self.check.setChecked(True)
        layout.addWidget(self.check)

        info = QVBoxLayout()
        info.setSpacing(3)

        # Shorten URL for display
        display_url = self.url if len(self.url) <= 72 else self.url[:69] + "…"
        url_lbl = QLabel(display_url)
        url_lbl.setObjectName("failed_url_lbl")
        url_lbl.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        url_lbl.setToolTip(self.url)
        info.addWidget(url_lbl)

        if self.error:
            display_err = self.error if len(self.error) <= 90 else self.error[:87] + "…"
            err_lbl = QLabel(f"⚠  {display_err}")
            err_lbl.setObjectName("failed_err_lbl")
            err_lbl.setFont(QFont("Inter", 8))
            err_lbl.setToolTip(self.error)
            info.addWidget(err_lbl)

        layout.addLayout(info, 1)
        self._apply_theme()

    def _apply_theme(self):
        t = self._theme
        self.setStyleSheet(f"""
            QWidget#failed_row {{
                background: {t['bg_tertiary']};
                border-radius: 8px;
                border: 1px solid {t['border']};
            }}
            QWidget#failed_row:hover {{
                background: {t['bg_hover']};
                border-color: #EF4444;
            }}
            QLabel#failed_url_lbl {{ color: {t['text_primary']}; }}
            QLabel#failed_err_lbl {{ color: #EF4444; }}
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


# ─────────────────────────────── Failed Downloads Dialog ────────────────────

class FailedDownloadsDialog(QDialog):
    """
    Popup listing all failed download URLs with checkboxes.
    Emits redownload_requested(urls) when the user confirms.
    """

    redownload_requested = Signal(list)   # list[str] of URLs to retry

    def __init__(self, failed_tasks: List[Dict], theme: dict, parent=None):
        """
        failed_tasks: list of dicts with keys 'url' and 'error'
        """
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setModal(True)

        self._theme = theme
        self._rows: List[FailedUrlRow] = []
        self._drag_pos = None

        self.setMinimumSize(620, 460)
        self.resize(680, 540)

        self._build(failed_tasks)
        self._apply_theme()
        self._center_on_parent(parent)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 8)
        self.main_container.setGraphicsEffect(shadow)

    # ──────────────────────────────────── Layout ─────────────────────────────

    def _build(self, failed_tasks: List[Dict]):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(0)

        self.main_container = QWidget()
        self.main_container.setObjectName("fd_container")
        container_layout = QVBoxLayout(self.main_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        container_layout.addWidget(self._build_titlebar())

        body = QWidget()
        body.setObjectName("fd_body")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 10, 14, 10)
        body_layout.setSpacing(8)

        # Summary label
        n = len(failed_tasks)
        self.summary_lbl = QLabel(
            f"❌  {n} download{'s' if n != 1 else ''} failed — select URLs to retry"
        )
        self.summary_lbl.setObjectName("fd_summary")
        self.summary_lbl.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        body_layout.addWidget(self.summary_lbl)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.select_all_check = QCheckBox("Select All")
        self.select_all_check.setChecked(True)
        self.select_all_check.setTristate(True)
        self.select_all_check.setFont(QFont("Inter", 9))
        self.select_all_check.clicked.connect(self._toggle_select_all)
        toolbar.addWidget(self.select_all_check)

        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("fd_count")
        self.count_lbl.setFont(QFont("Inter", 8))
        toolbar.addWidget(self.count_lbl)

        toolbar.addStretch()

        self.retry_btn = QPushButton("🔄  Redownload Selected")
        self.retry_btn.setObjectName("fd_retry_btn")
        self.retry_btn.setFixedHeight(36)
        self.retry_btn.setCursor(Qt.PointingHandCursor)
        self.retry_btn.clicked.connect(self._on_retry_clicked)
        toolbar.addWidget(self.retry_btn)

        toolbar_widget = QWidget()
        toolbar_widget.setLayout(toolbar)
        body_layout.addWidget(toolbar_widget)

        # Separator
        sep = QFrame()
        sep.setObjectName("fd_sep")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        body_layout.addWidget(sep)

        # Scrollable list
        scroll = QScrollArea()
        scroll.setObjectName("fd_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.list_widget = QWidget()
        self.list_widget.setObjectName("fd_list")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(5)

        for task in failed_tasks:
            row = FailedUrlRow(task["url"], task.get("error", ""), self._theme)
            row.check.stateChanged.connect(self._update_count)
            self._rows.append(row)
            self.list_layout.addWidget(row)

        self.list_layout.addStretch()
        scroll.setWidget(self.list_widget)
        body_layout.addWidget(scroll)

        container_layout.addWidget(body)
        root_layout.addWidget(self.main_container)

        self._update_count()

    def _build_titlebar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("fd_titlebar")
        bar.setFixedHeight(52)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 10, 0)
        layout.setSpacing(6)

        icon = QLabel("❌")
        icon.setFont(QFont("Segoe UI", 14))
        layout.addWidget(icon)

        title = QLabel("Failed Downloads")
        title.setObjectName("fd_title")
        title.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        layout.addWidget(title, 1)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("fd_close_btn")
        close_btn.setFixedSize(32, 32)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn)

        return bar

    # ──────────────────────────────────── Logic ──────────────────────────────

    def _toggle_select_all(self, checked: bool):
        current = self.select_all_check.checkState()
        want_all = (current != Qt.Unchecked)

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

        self.retry_btn.setEnabled(selected > 0)

    def _on_retry_clicked(self):
        urls = [r.url for r in self._rows if r.is_selected()]
        if not urls:
            return
        self.redownload_requested.emit(urls)
        self.retry_btn.setText(f"✅  {len(urls)} URL{'s' if len(urls) != 1 else ''} queued!")
        self.retry_btn.setEnabled(False)
        QTimer.singleShot(900, self.accept)

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

    def _center_on_parent(self, parent):
        if parent:
            pg = parent.geometry()
            sg = self.geometry()
            x = pg.x() + (pg.width() - sg.width()) // 2
            y = pg.y() + (pg.height() - sg.height()) // 2
            self.move(x, y)

    # ──────────────────────────────────── Theme ──────────────────────────────

    def _apply_theme(self):
        t = self._theme
        self.setStyleSheet(f"""
            QWidget#fd_container {{
                background: {t['bg_card']};
                border-radius: 18px;
                border: 1px solid {t['border']};
            }}
            QWidget#fd_titlebar {{
                background: {t['bg_secondary']};
                border-radius: 18px 18px 0 0;
                border-bottom: 1px solid {t['border']};
            }}
            QLabel#fd_title   {{ color: {t['text_primary']}; }}
            QLabel#fd_summary {{ color: #EF4444; }}
            QLabel#fd_count   {{ color: {t['text_muted']}; }}
            QPushButton#fd_close_btn {{
                background: {t['bg_tertiary']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                color: {t['text_primary']};
                font-size: 12px;
            }}
            QPushButton#fd_close_btn:hover {{
                background: #EF4444;
                color: white;
                border-color: #EF4444;
            }}
            QPushButton#fd_retry_btn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #EF4444, stop:1 #F97316);
                border: none;
                border-radius: 10px;
                color: white;
                font-weight: bold;
                font-size: 10px;
                padding: 0 18px;
            }}
            QPushButton#fd_retry_btn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #DC2626, stop:1 #EA580C);
            }}
            QPushButton#fd_retry_btn:disabled {{
                background: {t['bg_tertiary']};
                color: {t['text_muted']};
            }}
            QFrame#fd_sep {{ background: {t['border']}; }}
            QScrollArea#fd_scroll {{ background: transparent; border: none; }}
            QWidget#fd_list  {{ background: transparent; }}
            QWidget#fd_body  {{ background: transparent; }}
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
                opacity: 0.6;
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

    def update_theme(self, theme: dict):
        self._theme = theme
        for row in self._rows:
            row.update_theme(theme)
        self._apply_theme()
