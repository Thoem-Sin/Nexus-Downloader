"""Animated UI components"""

import math
from pathlib import Path
from PySide6.QtWidgets import QFrame, QWidget, QPushButton, QLabel, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property, QRect, QPointF, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QColor, QLinearGradient, QRadialGradient, QFont, QPen, QPixmap, QTransform


class GlassCard(QFrame):
    """Modern glassmorphic card with hover animation"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        
        self.shadow = QGraphicsDropShadowEffect()
        self.shadow.setBlurRadius(20)
        self.shadow.setColor(QColor(0, 0, 0, 50))
        self.shadow.setOffset(0, 4)
        self.setGraphicsEffect(self.shadow)
        
    def enterEvent(self, event):
        self.shadow.setBlurRadius(30)
        self.shadow.setOffset(0, 8)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self.shadow.setBlurRadius(20)
        self.shadow.setOffset(0, 4)
        super().leaveEvent(event)


class AnimatedIcon(QWidget):
    """Animated icon with pulsing effect"""
    def __init__(self, icon_text="▶", parent=None):
        super().__init__(parent)
        self.icon_text = icon_text
        self._scale = 1.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._direction = 1
        self.setFixedSize(48, 48)
        
    def start_pulse(self):
        self._timer.start(30)
    
    def stop_pulse(self):
        self._timer.stop()
        self._scale = 1.0
        self.update()
    
    def _animate(self):
        self._scale += 0.02 * self._direction
        if self._scale >= 1.1:
            self._direction = -1
        elif self._scale <= 0.95:
            self._direction = 1
        self.update()
    
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        
        path = QPainterPath()
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = min(self.width(), self.height()) / 2 * self._scale
        path.addEllipse(center, radius, radius)
        
        gradient = QRadialGradient(center, radius)
        gradient.setColorAt(0, QColor(139, 92, 246, 80))
        gradient.setColorAt(1, QColor(139, 92, 246, 20))
        p.fillPath(path, gradient)
        
        p.setPen(QPen(QColor(139, 92, 246)))
        p.setFont(QFont("Segoe UI", int(24 * self._scale)))
        p.drawText(self.rect(), Qt.AlignCenter, self.icon_text)


class LogoAnimatedIcon(QWidget):
    """Displays the Nexus logo PNG with a smooth breathe + glow animation.

    The logo gently scales between 95 % and 105 % and a coloured radial
    glow pulses behind it — matching the existing AnimatedIcon rhythm but
    using the real brand image instead of an emoji.
    """

    def __init__(self, logo_path: str | None = None, size: int = 48, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

        # ── Resolve logo path ──────────────────────────────────────────────
        if logo_path is None:
            # Default: logo.png sits next to this file's package root
            here = Path(__file__).resolve().parent.parent
            logo_path = str(here / "logo.png")

        self._pixmap = QPixmap(logo_path)
        if self._pixmap.isNull():
            # Fallback: no image found — draw a gradient circle
            self._pixmap = None

        # ── Animation state ───────────────────────────────────────────────
        self._scale   = 1.0          # current scale factor
        self._glow    = 0.0          # 0.0 → 1.0  (glow intensity)
        self._t       = 0.0          # continuous time counter (radians)
        self._timer   = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ── Public API ────────────────────────────────────────────────────────

    def start_pulse(self):
        self._timer.start(16)        # ~60 fps

    def stop_pulse(self):
        self._timer.stop()
        self._scale = 1.0
        self._glow  = 0.0
        self.update()

    # ── Animation tick ────────────────────────────────────────────────────

    def _tick(self):
        self._t += 0.045             # ~2 s per full cycle at 60 fps
        # Smooth sine wave: scale 0.95 → 1.05, glow 0.3 → 1.0
        s = math.sin(self._t)
        self._scale = 1.0 + s * 0.05
        self._glow  = 0.65 + s * 0.35
        self.update()

    # ── Paint ─────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0

        # 1) Radial glow behind the logo
        glow_r = min(w, h) / 2.0 * 1.1
        glow = QRadialGradient(QPointF(cx, cy), glow_r)
        alpha_outer = int(self._glow * 40)
        alpha_inner = int(self._glow * 90)
        glow.setColorAt(0.0, QColor(80, 160, 255, alpha_inner))
        glow.setColorAt(0.5, QColor(139, 92, 246, alpha_outer))
        glow.setColorAt(1.0, QColor(139, 92, 246, 0))
        glow_path = QPainterPath()
        glow_path.addEllipse(QPointF(cx, cy), glow_r, glow_r)
        p.fillPath(glow_path, glow)

        # 2) Logo image (or fallback gradient circle)
        if self._pixmap and not self._pixmap.isNull():
            scaled_w = w * self._scale
            scaled_h = h * self._scale
            dst = QRectF(
                cx - scaled_w / 2,
                cy - scaled_h / 2,
                scaled_w,
                scaled_h,
            )
            p.drawPixmap(dst.toRect(), self._pixmap)
        else:
            # Fallback: gradient circle with "N"
            r = min(w, h) / 2 * self._scale
            circle = QPainterPath()
            circle.addEllipse(QPointF(cx, cy), r, r)
            grad = QRadialGradient(QPointF(cx, cy), r)
            grad.setColorAt(0, QColor(80, 160, 255, 220))
            grad.setColorAt(1, QColor(139, 92, 246, 180))
            p.fillPath(circle, grad)
            p.setPen(QPen(QColor(255, 255, 255, 230)))
            p.setFont(QFont("Inter", int(r * 0.9), QFont.Weight.Bold))
            p.drawText(self.rect(), Qt.AlignCenter, "N")


class GradientProgressBar(QWidget):
    """Modern gradient progress bar with smooth animation"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(4)
        self._value = 0.0
        self._animation = None
        
    def setValue(self, value):
        self._value = max(0.0, min(100.0, value))
        if self._animation:
            self._animation.stop()
        self.update()
    
    def animate_to(self, value):
        self._animation = QPropertyAnimation(self, b"value")
        self._animation.setDuration(500)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.setStartValue(self._value)
        self._animation.setEndValue(value)
        self._animation.start()
    
    def get_value(self):
        return self._value
    
    def set_value(self, value):
        self._value = value
        self.update()
    
    value = Property(float, get_value, set_value)
    
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        
        bg_path = QPainterPath()
        bg_path.addRoundedRect(r, 2, 2)
        p.fillPath(bg_path, QColor(39, 39, 42))
        
        if self._value > 0:
            fill_width = int(r.width() * self._value / 100.0)
            fill_rect = QRect(0, 0, fill_width, r.height())
            
            gradient = QLinearGradient(0, 0, fill_width, 0)
            gradient.setColorAt(0, QColor(139, 92, 246))
            gradient.setColorAt(1, QColor(236, 72, 153))
            
            fill_path = QPainterPath()
            fill_path.addRoundedRect(fill_rect, 2, 2)
            p.fillPath(fill_path, gradient)