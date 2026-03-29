"""
license_dialog.py  —  License Activation Dialog (Redesigned)
"""

import webbrowser

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QApplication, QGraphicsDropShadowEffect,
    QWidget,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QPoint
from PySide6.QtGui import QFont, QColor, QPainter, QPen

import license_client as lc

ADMIN_CONTACT = "https://t.me/YourAdminUsername"


# ══════════════════════════════════════════════════════════════════════════════
# Draggable header — drag lives HERE, not on the dialog
# ══════════════════════════════════════════════════════════════════════════════

class _DragHeader(QWidget):
    """Header bar that handles window dragging. Buttons inside are NOT blocked."""

    def __init__(self, dialog: QDialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self._drag_pos = QPoint()
        self._dragging = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Get the widget at the click position
            child = self.childAt(event.position().toPoint())
            
            # Check if we're clicking on a button or its children
            widget = child
            is_button = False
            while widget:
                if isinstance(widget, QPushButton):
                    is_button = True
                    break
                widget = widget.parentWidget()
            
            # Only start dragging if NOT on a button
            if not is_button:
                self._dragging = True
                self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() == Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._dialog.move(self._dialog.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self._drag_pos = QPoint()


# ══════════════════════════════════════════════════════════════════════════════
# Spinner
# ══════════════════════════════════════════════════════════════════════════════

class _Spinner(QWidget):
    def __init__(self, size: int = 18, color: str = "#ffffff", parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._angle = 0
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._timer.start(16)

    def stop(self):
        self._timer.stop()

    def _tick(self):
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2)
        track = QPen(QColor(255, 255, 255, 35), 2.5)
        track.setCapStyle(Qt.RoundCap)
        p.setPen(track)
        p.drawEllipse(r)
        arc = QPen(self._color, 2.5)
        arc.setCapStyle(Qt.RoundCap)
        p.setPen(arc)
        p.drawArc(r, (-self._angle) * 16, 270 * 16)
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
# Background thread
# ══════════════════════════════════════════════════════════════════════════════

class _ValidateThread(QThread):
    result = Signal(dict)

    def __init__(self, force_online: bool = True, parent=None):
        super().__init__(parent)
        self.force_online = force_online

    def run(self):
        self.result.emit(lc.validate_license(force_online=self.force_online))


# ══════════════════════════════════════════════════════════════════════════════
# Result popup
# ══════════════════════════════════════════════════════════════════════════════

class _ResultPopup(QDialog):
    def __init__(self, ok: bool, title: str, body: str, theme: dict, parent=None):
        super().__init__(parent)
        self.ok = ok
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumWidth(300)
        self._build(ok, title, body, theme)

    def _build(self, ok, title, body, theme):
        t = theme
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)

        card = QFrame()
        sh = QGraphicsDropShadowEffect()
        sh.setBlurRadius(32)
        sh.setColor(QColor(0, 0, 0, 100))
        sh.setOffset(0, 6)
        card.setGraphicsEffect(sh)
        card.setStyleSheet(f"""
            QFrame {{
                background: {t['bg_card']};
                border-radius: 16px;
                border: none;
            }}
            QLabel {{ color: {t['text_primary']}; background: transparent; }}
        """)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(10)

        icon_lbl = QLabel("✅" if ok else "❌")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 30))
        lay.addWidget(icon_lbl)

        t_lbl = QLabel(title)
        t_lbl.setAlignment(Qt.AlignCenter)
        t_lbl.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        lay.addWidget(t_lbl)

        b_lbl = QLabel(body)
        b_lbl.setAlignment(Qt.AlignCenter)
        b_lbl.setWordWrap(True)
        b_lbl.setFont(QFont("Inter", 9))
        b_lbl.setStyleSheet(f"color: {t['text_secondary']};")
        lay.addWidget(b_lbl)

        lay.addSpacing(6)

        ok_btn = QPushButton("OK")
        ok_btn.setFixedHeight(38)
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t['gradient_start']}, stop:1 {t['gradient_end']});
                color: white; border: none; border-radius: 8px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t['accent_hover']}, stop:1 #F472B6);
            }}
        """)
        ok_btn.clicked.connect(self.accept)
        lay.addWidget(ok_btn)

        outer.addWidget(card)


# ══════════════════════════════════════════════════════════════════════════════
# Main Dialog
# ══════════════════════════════════════════════════════════════════════════════

class LicenseDialog(QDialog):
    """
    allow_close=False  → startup guard; ✕ exits the app.
    allow_close=True   → from menu; ✕ just dismisses.
    """

    def __init__(self, parent=None, allow_close: bool = False, theme: dict = None):
        super().__init__(parent)
        self.allow_close = allow_close
        self.theme = theme or {
            "bg_primary":       "#0A0A0F",
            "bg_secondary":     "#111118",
            "bg_tertiary":      "#16161F",
            "bg_card":          "#1C1C27",
            "bg_hover":         "#24242F",
            "bg_input":         "#0F0F16",
            "border":           "#2A2A38",
            "border_focus":     "#7C3AED",
            "accent":           "#8B5CF6",
            "accent_hover":     "#9F6EFF",
            "accent_secondary": "#EC489A",
            "text_primary":     "#F9FAFB",
            "text_secondary":   "#9CA3AF",
            "text_muted":       "#6B7280",
            "gradient_start":   "#8B5CF6",
            "gradient_end":     "#EC489A",
            "glass":            "rgba(28,28,39,0.95)",
        }
        self._thread: _ValidateThread | None = None
        self._license_ok = False

        self.setWindowTitle("Activation")
        self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(440, 340)

        self._build_ui()
        self._apply_styles()

    # ── Build UI ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)

        self._container = QFrame()
        self._container.setObjectName("container")
        sh = QGraphicsDropShadowEffect()
        sh.setBlurRadius(40)
        sh.setColor(QColor(0, 0, 0, 110))
        sh.setOffset(0, 8)
        self._container.setGraphicsEffect(sh)

        root = QVBoxLayout(self._container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._make_header())
        root.addWidget(self._make_body())

        outer.addWidget(self._container)

    def _make_header(self):
        # Use _DragHeader so dragging works but buttons are never blocked
        header = _DragHeader(self)
        header.setObjectName("header")
        header.setFixedHeight(50)
        lay = QHBoxLayout(header)
        lay.setContentsMargins(20, 0, 14, 0)

        icon = QLabel("🔐")
        icon.setFont(QFont("Segoe UI Emoji", 13))
        lay.addWidget(icon)

        title = QLabel("License Activation")
        title.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        lay.addWidget(title)
        lay.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setObjectName("close_btn")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFocusPolicy(Qt.NoFocus)
        # Direct connection — no lambda, no indirection
        if self.allow_close:
            close_btn.clicked.connect(self.reject)
        else:
            close_btn.clicked.connect(QApplication.quit)
        lay.addWidget(close_btn)
        return header

    def _make_body(self):
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 20, 28, 22)
        lay.setSpacing(14)

        lay.addWidget(self._cap_label("Machine ID"))
        lay.addWidget(self._make_mid_row())
        lay.addWidget(self._cap_label("License Key"))
        lay.addWidget(self._make_key_row())
        lay.addStretch()
        lay.addWidget(self._make_buttons())
        return body

    def _cap_label(self, text: str) -> QLabel:
        t = self.theme
        lbl = QLabel(text.upper())
        lbl.setFont(QFont("Inter", 7, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {t['text_muted']}; letter-spacing: 1.5px;")
        return lbl

    def _make_mid_row(self):
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._mid_edit = QLineEdit(lc.get_machine_id())
        self._mid_edit.setReadOnly(True)
        self._mid_edit.setObjectName("mid_edit")
        self._mid_edit.setFixedHeight(36)
        self._mid_edit.setFont(QFont("Consolas,Courier New", 10))

        self._copy_btn = QPushButton("Copy")
        self._copy_btn.setObjectName("secondary_btn")
        self._copy_btn.setFixedSize(66, 36)
        self._copy_btn.setCursor(Qt.PointingHandCursor)
        self._copy_btn.clicked.connect(self._copy_mid)

        lay.addWidget(self._mid_edit, 1)
        lay.addWidget(self._copy_btn)
        return row

    def _make_key_row(self):
        saved = lc.load_saved_license()
        self._key_edit = QLineEdit()
        self._key_edit.setObjectName("key_edit")
        self._key_edit.setPlaceholderText("TIKDL-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX")
        self._key_edit.setFont(QFont("Consolas,Courier New", 9))
        self._key_edit.setFixedHeight(38)
        if saved["key"]:
            self._key_edit.setText(saved["key"])
        self._key_edit.returnPressed.connect(self._on_activate)
        return self._key_edit

    def _make_buttons(self):
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self._admin_btn = QPushButton("Contact Admin")
        self._admin_btn.setObjectName("secondary_btn")
        self._admin_btn.setFixedHeight(40)
        self._admin_btn.setCursor(Qt.PointingHandCursor)
        self._admin_btn.clicked.connect(self._contact_admin)
        lay.addWidget(self._admin_btn, 1)

        self._activate_btn = QPushButton()
        self._activate_btn.setObjectName("activate_btn")
        self._activate_btn.setFixedHeight(40)
        self._activate_btn.setCursor(Qt.PointingHandCursor)
        self._activate_btn.clicked.connect(self._on_activate)

        btn_inner = QHBoxLayout(self._activate_btn)
        btn_inner.setContentsMargins(14, 0, 14, 0)
        btn_inner.setSpacing(8)
        btn_inner.setAlignment(Qt.AlignCenter)

        self._spinner = _Spinner(18, "#ffffff")
        self._spinner.hide()
        btn_inner.addWidget(self._spinner)

        self._act_lbl = QLabel("Activate")
        self._act_lbl.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        self._act_lbl.setStyleSheet("color: white; background: transparent;")
        btn_inner.addWidget(self._act_lbl)

        lay.addWidget(self._activate_btn, 1)
        return row

    # ── Styles ─────────────────────────────────────────────────────────────────

    def _apply_styles(self):
        t = self.theme
        self.setStyleSheet(f"""
            QDialog {{ background: transparent; }}

            QFrame#container {{
                background: {t['bg_card']};
                border-radius: 18px;
                border: 1px solid {t['border']};
            }}
            QWidget#header {{
                background: {t['bg_secondary']};
                border-top-left-radius: 18px;
                border-top-right-radius: 18px;
                border-bottom: 1px solid {t['border']};
            }}
            QLabel {{
                color: {t['text_primary']};
                background: transparent;
            }}
            QLineEdit {{
                background: {t['bg_input']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                color: {t['text_primary']};
                padding: 4px 12px;
                selection-background-color: {t['accent']};
            }}
            QLineEdit:focus {{ border-color: {t['border_focus']}; }}
            QLineEdit#mid_edit {{ color: {t['text_secondary']}; }}

            QPushButton#close_btn {{
                background: transparent;
                border: none;
                color: {t['text_muted']};
                font-size: 11px;
                border-radius: 6px;
            }}
            QPushButton#close_btn:hover {{ background: #EF4444; color: white; }}

            QPushButton#secondary_btn {{
                background: {t['bg_tertiary']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                color: {t['text_secondary']};
                font-size: 10px;
                font-weight: 500;
            }}
            QPushButton#secondary_btn:hover {{
                background: {t['bg_hover']};
                border-color: {t['accent']};
                color: {t['text_primary']};
            }}
            QPushButton#secondary_btn:disabled {{ opacity: 0.45; }}

            QPushButton#activate_btn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t['gradient_start']}, stop:1 {t['gradient_end']});
                border: none;
                border-radius: 8px;
            }}
            QPushButton#activate_btn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t['accent_hover']}, stop:1 #F472B6);
            }}
            QPushButton#activate_btn:disabled {{ opacity: 0.5; }}
        """)

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _copy_mid(self):
        QApplication.clipboard().setText(self._mid_edit.text())
        self._copy_btn.setText("✓ OK")
        QTimer.singleShot(1800, lambda: self._copy_btn.setText("Copy"))

    def _contact_admin(self):
        webbrowser.open(ADMIN_CONTACT)

    def _on_activate(self):
        key = self._key_edit.text().strip().upper()
        if not key:
            self._key_edit.setFocus()
            return

        lc.save_license_key(key)
        self._set_loading(True)

        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()

        self._thread = _ValidateThread(force_online=True, parent=self)
        self._thread.result.connect(self._on_result)
        self._thread.start()

    def _set_loading(self, on: bool):
        self._activate_btn.setEnabled(not on)
        self._admin_btn.setEnabled(not on)
        self._key_edit.setEnabled(not on)
        self._copy_btn.setEnabled(not on)
        if on:
            self._spinner.show()
            self._spinner.start()
            self._act_lbl.setText("Checking…")
        else:
            self._spinner.stop()
            self._spinner.hide()
            self._act_lbl.setText("Activate")

    def _on_result(self, r: dict):
        self._set_loading(False)
        self._license_ok = r.get("ok", False)

        ok     = self._license_ok
        status = r.get("status", "")
        reason = r.get("reason", "")
        days   = r.get("days_left", 0)
        exp    = r.get("expires", "")

        if ok:
            pop_title = "License Activated!"
            pop_body  = (
                f"Your license is valid.\nExpires: {exp}  ({days} days remaining)"
                if days >= 0
                else "Your license is valid."
            )
        else:
            pop_title = {
                "no_key":           "No License Key",
                "expired":          "License Expired",
                "invalid":          "Invalid Key",
                "machine_mismatch": "Wrong Machine",
                "revoked":          "License Revoked",
                "not_found":        "Key Not Found",
            }.get(status, "Activation Failed")
            pop_body = reason or "Could not verify the license. Please try again."

        popup = _ResultPopup(ok, pop_title, pop_body, self.theme, parent=self)
        popup.finished.connect(self._on_popup_done)
        popup.exec()

    def _on_popup_done(self, _result):
        if self._license_ok:
            self.accept()

    def closeEvent(self, event):
        if not self.allow_close:
            QApplication.quit()
        super().closeEvent(event)