"""Settings dialog – matches the solid-card theme used by _NoInternetDialog."""

import sys
import os
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                               QWidget, QLabel, QSpinBox, QCheckBox,
                               QPushButton, QFrame, QSlider,
                               QLineEdit, QComboBox, QScrollArea,
                               QFileDialog, QGraphicsDropShadowEffect)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont, QColor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Shared constants ──────────────────────────────────────────────────────────
_FONT   = "Inter"
_F_BODY = 9       # body / labels
_F_SEC  = 9       # section titles (bold)
_F_HEAD = 11      # dialog title (bold)
MARGIN  = 18      # transparent margin so drop-shadow has room


# ── Minimal slider ────────────────────────────────────────────────────────────
class ModernSlider(QSlider):
    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 3px;
                background: rgba(128,128,128,0.3);
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #7C6AF7;
                width: 13px; height: 13px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover { background: #9580FF; }
            QSlider::sub-page:horizontal {
                background: #7C6AF7;
                border-radius: 2px;
            }
        """)


# ── Settings dialog ───────────────────────────────────────────────────────────
class SettingsDialog(QDialog):

    def __init__(self, settings_manager, current_theme, parent=None):
        super().__init__(parent)
        self.settings      = settings_manager
        self.current_theme = current_theme
        self._drag_pos     = QPoint()
        self._dragging     = False

        self.setWindowTitle("Settings")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # card 400x460 + MARGIN on each side
        self.setFixedSize(400 + MARGIN * 2, 460 + MARGIN * 2)

        self._build()
        self.load_settings()

    # ── drag ──────────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self._dragging and e.buttons() == Qt.LeftButton:
            delta = e.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        self._dragging = False

    # ── centering ─────────────────────────────────────────────────────────────
    def showEvent(self, event):
        super().showEvent(event)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(10, self._center)

    def _center(self):
        if self.parent():
            pg = self.parent().geometry()
            self.move(
                pg.x() + (pg.width()  - self.width())  // 2,
                pg.y() + (pg.height() - self.height()) // 2,
            )

    # ── build ─────────────────────────────────────────────────────────────────
    def _build(self):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 160))

        self.card = QWidget(self)
        self.card.setGeometry(MARGIN, MARGIN, 400, 460)
        self.card.setObjectName("settings_card")
        self.card.setGraphicsEffect(shadow)

        root = QVBoxLayout(self.card)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        div = QFrame(); div.setFrameShape(QFrame.HLine); div.setObjectName("hdr_divider")
        root.addWidget(div)

        root.addWidget(self._build_body(), 1)

        div2 = QFrame(); div2.setFrameShape(QFrame.HLine); div2.setObjectName("hdr_divider")
        root.addWidget(div2)

        root.addWidget(self._build_footer())

        self._apply_stylesheet()

    # ── header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = QWidget(); hdr.setObjectName("dlg_header"); hdr.setFixedHeight(46)
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(16, 0, 12, 0); lay.setSpacing(8)

        self.lbl_title = QLabel("⚙️  Settings")
        self.lbl_title.setFont(QFont(_FONT, _F_HEAD, QFont.Bold))
        lay.addWidget(self.lbl_title)
        lay.addStretch()

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("dlg_close_btn")
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.reject)
        lay.addWidget(self.close_btn)
        return hdr

    # ── body ──────────────────────────────────────────────────────────────────
    def _build_body(self):
        scroll = QScrollArea()
        scroll.setObjectName("dlg_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget(); inner.setObjectName("dlg_inner")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(8)

        lay.addWidget(self._section_download())
        lay.addWidget(self._section_quality())
        lay.addWidget(self._section_advanced())
        lay.addStretch()

        scroll.setWidget(inner)
        return scroll

    # ── footer ────────────────────────────────────────────────────────────────
    def _build_footer(self):
        ftr = QWidget(); ftr.setObjectName("dlg_footer"); ftr.setFixedHeight(46)
        lay = QHBoxLayout(ftr)
        lay.setContentsMargins(14, 6, 14, 6); lay.setSpacing(8)
        lay.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("btn_secondary")
        self.cancel_btn.setFixedSize(80, 30)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.reject)
        lay.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save Changes")
        self.save_btn.setObjectName("btn_primary")
        self.save_btn.setFixedSize(100, 30)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self.save_settings)
        lay.addWidget(self.save_btn)
        return ftr

    # ── section helpers ───────────────────────────────────────────────────────
    def _section(self, title):
        frame = QFrame(); frame.setObjectName("settings_section")
        vlay = QVBoxLayout(frame)
        vlay.setContentsMargins(12, 8, 12, 10); vlay.setSpacing(5)

        lbl = QLabel(title)
        lbl.setFont(QFont(_FONT, _F_SEC, QFont.Bold))
        lbl.setObjectName("section_title")
        vlay.addWidget(lbl)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setObjectName("sec_sep")
        vlay.addWidget(sep)

        return frame, vlay

    def _row(self, label_text, widget, lbl_w=130):
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(8)
        lbl = QLabel(label_text)
        lbl.setFont(QFont(_FONT, _F_BODY))
        lbl.setObjectName("row_lbl")
        if lbl_w: lbl.setFixedWidth(lbl_w)
        lay.addWidget(lbl); lay.addStretch(); lay.addWidget(widget)
        return row

    # ── Download section ──────────────────────────────────────────────────────
    def _section_download(self):
        frame, lay = self._section("📥  Download Settings")

        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setFixedWidth(58)
        self.concurrent_spin.setFont(QFont(_FONT, _F_BODY))

        self.concurrent_slider = ModernSlider(Qt.Horizontal)
        self.concurrent_slider.setRange(1, 10)
        self.concurrent_slider.setFixedWidth(130)
        self.concurrent_slider.valueChanged.connect(self.concurrent_spin.setValue)
        self.concurrent_spin.valueChanged.connect(self.concurrent_slider.setValue)

        conc = QWidget()
        cl = QHBoxLayout(conc); cl.setContentsMargins(0,0,0,0); cl.setSpacing(8)
        l = QLabel("Concurrent Downloads"); l.setFont(QFont(_FONT, _F_BODY)); l.setObjectName("row_lbl")
        cl.addWidget(l); cl.addStretch()
        cl.addWidget(self.concurrent_slider); cl.addWidget(self.concurrent_spin)
        lay.addWidget(conc)

        self.folder_path = QLineEdit()
        self.folder_path.setReadOnly(True)
        self.folder_path.setFont(QFont(_FONT, _F_BODY))
        self.folder_path.setFixedHeight(26)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setObjectName("btn_secondary")
        self.browse_btn.setFixedSize(60, 26)
        self.browse_btn.setFont(QFont(_FONT, _F_BODY))
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        self.browse_btn.clicked.connect(self._browse_folder)

        fold = QWidget()
        fl = QHBoxLayout(fold); fl.setContentsMargins(0,0,0,0); fl.setSpacing(8)
        fl2 = QLabel("Download Location"); fl2.setFont(QFont(_FONT, _F_BODY))
        fl2.setObjectName("row_lbl"); fl2.setFixedWidth(120)
        fl.addWidget(fl2); fl.addWidget(self.folder_path, 1); fl.addWidget(self.browse_btn)
        lay.addWidget(fold)

        self.auto_subfolder_check = QCheckBox("Auto-create subfolder for channels/playlists")
        self.auto_subfolder_check.setFont(QFont(_FONT, _F_BODY))
        lay.addWidget(self.auto_subfolder_check)

        return frame

    # ── Quality section ───────────────────────────────────────────────────────
    def _section_quality(self):
        frame, lay = self._section("🎬  Default Quality")

        self.default_quality = QComboBox()
        self.default_quality.addItems(["Best","2160p","1440p","1080p","720p","480p","360p"])
        self.default_quality.setFixedWidth(90)
        self.default_quality.setFont(QFont(_FONT, _F_BODY))
        lay.addWidget(self._row("Video Quality", self.default_quality))

        self.default_format = QComboBox()
        self.default_format.addItems(["MP4","MKV","WEBM","MP3","M4A"])
        self.default_format.setFixedWidth(90)
        self.default_format.setFont(QFont(_FONT, _F_BODY))
        lay.addWidget(self._row("Default Format", self.default_format))

        return frame

    # ── Advanced section ──────────────────────────────────────────────────────
    def _section_advanced(self):
        frame, lay = self._section("⚡  Advanced")

        for attr, text in [
            ("default_subs",       "Download subtitles by default"),
            ("download_thumbnail", "Embed thumbnail in video"),
            ("embed_metadata",     "Embed metadata (title, uploader, etc.)"),
        ]:
            cb = QCheckBox(text); cb.setFont(QFont(_FONT, _F_BODY))
            setattr(self, attr, cb); lay.addWidget(cb)

        return frame

    # ── stylesheet ────────────────────────────────────────────────────────────
    def _apply_stylesheet(self):
        t = self.current_theme
        a = t.get("accent", "#7C6AF7")

        self.card.setStyleSheet(f"""
            QWidget#settings_card {{
                background: {t['bg_card']};
                border: 1px solid {t['border']};
                border-radius: 14px;
            }}
            QWidget#dlg_header, QWidget#dlg_footer, QWidget#dlg_inner {{
                background: transparent;
            }}
            QFrame#hdr_divider, QFrame#sec_sep {{
                color: {t['border']}; background: {t['border']};
                max-height: 1px; border: none;
            }}
            QScrollArea#dlg_scroll {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 5px; border-radius: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {t.get('scrollbar','rgba(128,128,128,0.4)')};
                border-radius: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t.get('scrollbar_hover','rgba(128,128,128,0.6)')};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

            QFrame#settings_section {{
                background: {t['bg_secondary']};
                border: 1px solid {t['border']};
                border-radius: 10px;
            }}

            QLabel {{
                background: transparent; border: none;
                color: {t['text_primary']}; font-size: {_F_BODY}pt;
            }}
            QLabel#section_title {{
                font-size: {_F_SEC}pt; font-weight: bold;
            }}
            QLabel#row_lbl {{ color: {t['text_secondary']}; }}

            QPushButton#dlg_close_btn {{
                background: {t['bg_tertiary']}; border: 1px solid {t['border']};
                border-radius: 7px; color: {t['text_primary']}; font-size: {_F_BODY}pt;
            }}
            QPushButton#dlg_close_btn:hover {{
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
                background: {a}; border: none; border-radius: 7px;
                color: white; font-size: {_F_BODY}pt; font-weight: bold;
            }}
            QPushButton#btn_primary:hover {{ background: #9580FF; }}

            QLineEdit {{
                background: {t['bg_input']}; border: 1px solid {t['border']};
                border-radius: 6px; color: {t['text_primary']};
                padding: 2px 6px; font-size: {_F_BODY}pt;
            }}
            QLineEdit:focus {{ border-color: {a}; }}

            QSpinBox {{
                background: {t['bg_input']}; border: 1px solid {t['border']};
                border-radius: 6px; color: {t['text_primary']};
                padding: 2px 4px; font-size: {_F_BODY}pt;
            }}
            QSpinBox:hover {{ border-color: {a}; }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background: {t['bg_tertiary']}; border: none; width: 14px;
            }}

            QComboBox {{
                background: {t['bg_input']}; border: 1px solid {t['border']};
                border-radius: 6px; color: {t['text_primary']};
                padding: 2px 6px; font-size: {_F_BODY}pt;
            }}
            QComboBox:hover {{ border-color: {a}; }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{
                background: {t['bg_card']}; border: 1px solid {t['border']};
                color: {t['text_primary']};
                selection-background-color: {a}; selection-color: white;
            }}

            QCheckBox {{
                color: {t['text_primary']}; font-size: {_F_BODY}pt; spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 15px; height: 15px; border-radius: 3px;
                border: 2px solid {t['border']}; background: {t['bg_input']};
            }}
            QCheckBox::indicator:checked {{
                background: {a}; border-color: {a};
            }}
        """)

    # ── data ──────────────────────────────────────────────────────────────────
    def load_settings(self):
        g = lambda k, d: self.settings.get(k, d)
        self.concurrent_spin.setValue(int(g("concurrent_downloads", 3)))
        self.concurrent_slider.setValue(int(g("concurrent_downloads", 3)))
        self.auto_subfolder_check.setChecked(g("auto_create_subfolders", True))
        self.folder_path.setText(g("output_dir", ""))
        q = {"best":0,"2160":1,"1440":2,"1080":3,"720":4,"480":5,"360":6}
        self.default_quality.setCurrentIndex(q.get(g("default_quality","best"), 0))
        f = {"mp4":0,"mkv":1,"webm":2,"mp3":3,"m4a":4}
        self.default_format.setCurrentIndex(f.get(g("default_format","mp4"), 0))
        self.default_subs.setChecked(g("default_subtitles", False))
        self.download_thumbnail.setChecked(g("download_thumbnail", True))
        self.embed_metadata.setChecked(g("embed_metadata", True))

    def save_settings(self):
        s = self.settings
        s.set("concurrent_downloads",   self.concurrent_spin.value())
        s.set("auto_create_subfolders", self.auto_subfolder_check.isChecked())
        s.set("output_dir",             self.folder_path.text())
        s.set("default_quality",        ["best","2160","1440","1080","720","480","360"][self.default_quality.currentIndex()])
        s.set("default_format",         ["mp4","mkv","webm","mp3","m4a"][self.default_format.currentIndex()])
        s.set("default_subtitles",      self.default_subs.isChecked())
        s.set("download_thumbnail",     self.download_thumbnail.isChecked())
        s.set("embed_metadata",         self.embed_metadata.isChecked())
        self.accept()

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if folder:
            self.folder_path.setText(folder)

    def update_theme(self, new_theme):
        self.current_theme = new_theme
        self._apply_stylesheet()