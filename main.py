#!/usr/bin/env python3
"""
Nexus Downloader - PySide6 Application
A feature-rich video downloader with modern glassmorphic design
"""
import os
import sys
import socket
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QDialog, QWidget, QVBoxLayout,
                                QHBoxLayout, QLabel, QPushButton,
                                QGraphicsDropShadowEffect)
from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QFont, QIcon, QColor
from main_window import ModernMainWindow

# ── License ────────────────────────────────────────────────────────────────────
from license_client import validate_license
from license_dialog import LicenseDialog


# ══════════════════════════════════════════════════════════════════════════════
# No-Internet dialog
# ══════════════════════════════════════════════════════════════════════════════

class _NoInternetDialog(QDialog):
    """Shown at startup when no internet connection is detected."""

    _THEME = {
        "bg_primary":   "#0A0A0F",
        "bg_card":      "#1C1C27",
        "bg_secondary": "#111118",
        "border":       "#2A2A38",
        "accent":       "#7C6AF7",
        "text_primary": "#E8E8F0",
        "text_secondary": "#A0A0B8",
        "text_muted":   "#606078",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(340, 200)
        self._drag_pos = QPoint()
        self._dragging = False
        self._build()

    # ── drag support ──────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() == Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._dragging = False

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build(self):
        t = self._THEME

        # Drop shadow applied to the card only (not the dialog itself).
        # This avoids UpdateLayeredWindowIndirect errors where Qt needs the
        # shadow bleed area to fit inside the transparent window bounds.
        MARGIN = 18
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 160))

        card = QWidget(self)
        card.setGeometry(MARGIN, MARGIN, 340 - MARGIN * 2, 200 - MARGIN * 2)
        card.setGraphicsEffect(shadow)
        card.setStyleSheet(f"""
            QWidget#no_internet_card {{
                background: {t['bg_card']};
                border: 1px solid {t['border']};
                border-radius: 14px;
            }}
            QLabel {{
                background: transparent;
                border: none;
                color: {t['text_primary']};
            }}
        """)
        card.setObjectName("no_internet_card")

        root = QVBoxLayout(card)
        root.setContentsMargins(18, 14, 18, 12)
        root.setSpacing(0)

        # Icon + title row
        title_row = QHBoxLayout()
        title_row.setSpacing(12)

        icon_lbl = QLabel("⚡")
        icon_lbl.setFont(QFont("Segoe UI Emoji", 20))
        icon_lbl.setFixedSize(36, 36)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("""
            background: rgba(255,85,85,0.15);
            border: 1px solid rgba(255,85,85,0.3);
            border-radius: 10px;
        """)
        title_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        h1 = QLabel("No Internet Connection")
        h1.setFont(QFont("Inter", 11, QFont.Bold))
        h1.setStyleSheet(f"color: {t['text_primary']}; border: none;")
        title_col.addWidget(h1)

        sub = QLabel("Nexus Downloader requires internet to start.")
        sub.setFont(QFont("Inter", 8))
        sub.setStyleSheet(f"color: {t['text_secondary']}; border: none;")
        title_col.addWidget(sub)

        title_row.addLayout(title_col)
        title_row.addStretch()
        root.addLayout(title_row)
        root.addSpacing(12)

        # Body message
        body = QLabel(
            "Please check your network connection and click "
            "<b>Retry</b> to try again, or <b>Exit</b> to close the application."
        )
        body.setFont(QFont("Inter", 9))
        body.setStyleSheet(f"color: {t['text_secondary']}; border: none;")
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText)
        root.addWidget(body)
        root.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        exit_btn = QPushButton("Exit")
        exit_btn.setFixedSize(78, 32)
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setFont(QFont("Inter", 9))
        exit_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t['bg_secondary']};
                color: {t['text_secondary']};
                border: 1px solid {t['border']};
                border-radius: 7px;
            }}
            QPushButton:hover {{ background: {t['bg_primary']}; color: {t['text_primary']}; }}
        """)
        exit_btn.clicked.connect(self.reject)
        btn_row.addWidget(exit_btn)

        retry_btn = QPushButton("⟳  Retry")
        retry_btn.setFixedSize(96, 32)
        retry_btn.setCursor(Qt.PointingHandCursor)
        retry_btn.setFont(QFont("Inter", 9, QFont.Bold))
        retry_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t['accent']};
                color: white;
                border: none;
                border-radius: 7px;
            }}
            QPushButton:hover {{ background: #9580FF; }}
        """)
        retry_btn.clicked.connect(self.accept)
        btn_row.addWidget(retry_btn)

        root.addLayout(btn_row)


def _is_connected() -> bool:
    """Return True if the machine can reach the internet."""
    try:
        socket.setdefaulttimeout(3)
        socket.create_connection(("8.8.8.8", 53))
        return True
    except OSError:
        return False


def _check_internet(app: QApplication) -> bool:
    """
    Block startup until internet is available.
    Shows a styled dialog with Retry / Exit.
    Returns True when connected, False if user chose Exit.
    """
    while not _is_connected():
        dlg = _NoInternetDialog()
        result = dlg.exec()
        if result != QDialog.Accepted:
            # User clicked Exit
            return False
        # User clicked Retry — loop and check again
    return True


def _check_license(app: QApplication) -> bool:
    """
    Validate license on startup.

    Strategy:
    - Always attempt an online check first (catches revocations immediately).
    - If the server is unreachable AND we have a recent valid cache → allow
      (offline_grace).
    - If the server returns ok=False (revoked/expired) → block regardless of
      any cached state.
    - If no key or invalid → show the license dialog.
    """
    # Force online so revocations take effect immediately
    result = validate_license(force_online=True)
    status = result.get("status", "")

    if result.get("ok") and status in ("active", "offline_grace", "offline_valid"):
        return True  # valid — proceed

    # Server said explicitly revoked / expired → block, no dialog bypass
    if status in ("revoked", "expired", "banned"):
        from auto_updater import InfoDialog
        # Need a temporary QWidget parent — create a minimal one
        dlg = LicenseDialog(allow_close=False)
        from PySide6.QtWidgets import QMessageBox
        # Show the license dialog so user can enter a new key
        if dlg.exec() != QDialog.Accepted:
            app.quit()
            return False
        return True

    # No key, invalid key, or any other failure → show dialog
    dlg = LicenseDialog(allow_close=False)
    if dlg.exec() != QDialog.Accepted:
        app.quit()
        return False
    return True


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Nexus Downloader")
    app.setOrganizationName("NexusLabs")

    font = QFont("Inter")
    font.setPointSize(9)          # consistent base size for all widgets
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    # ── App icon (taskbar, Alt+Tab, EXE) ──
    _base = Path(__file__).parent
    _ico  = _base / "Icon.ico"
    _png  = _base / "logo.png"
    icon_path = str(_ico) if _ico.exists() else str(_png) if _png.exists() else None
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    # ── Internet gate (must come before license check) ──
    if not _check_internet(app):
        sys.exit(0)

    # ── License gate ──
    if not _check_license(app):
        sys.exit(0)

    window = ModernMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()