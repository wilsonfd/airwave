# -*- coding: utf-8 -*-
"""Custom-painted widgets: the difference between a prototype and a real app."""
from __future__ import annotations

import math
import time
from collections import deque
from typing import List, Optional, Sequence

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QConicalGradient, QFont, QFontMetrics, QPainter, QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QFrame, QLabel, QPlainTextEdit, QSizePolicy, QVBoxLayout, QWidget,
)

from . import theme


def _rgba(hex_color: str, alpha: int) -> QColor:
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c


class StatusPill(QWidget):
    """Small status capsule with a breathing dot."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._text = "未运行"
        self._color = QColor(theme.MUTED)
        self._active = False
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._tick)
        self.setFixedHeight(30)

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(QFont("Microsoft YaHei UI", 9, QFont.Weight.DemiBold))
        return QSize(fm.horizontalAdvance(self._text) + 46, 30)

    def set_state(self, text: str, color: str, active: bool = False) -> None:
        self._text = text
        self._color = QColor(color)
        self._active = active
        if active and not self._timer.isActive():
            self._timer.start()
        elif not active:
            self._timer.stop()
            self._phase = 0.0
        self.updateGeometry()
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.11) % (math.pi * 2)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        rect = QRectF(0.5, 0.5, w - 1, h - 1)
        fill = QColor(self._color)
        fill.setAlpha(24)
        border = QColor(self._color)
        border.setAlpha(80)
        p.setBrush(fill)
        p.setPen(QPen(border, 1))
        p.drawRoundedRect(rect, h / 2, h / 2)

        pulse = 0.5 + 0.5 * math.sin(self._phase) if self._active else 1.0
        dot = QColor(self._color)
        dot.setAlpha(int(150 + 105 * pulse) if self._active else 220)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(dot)
        r = 3.4 if not self._active else 3.0 + 0.9 * pulse
        p.drawEllipse(QPointF(16, h / 2), r, r)

        p.setPen(QColor(theme.TEXT_SOFT))
        p.setFont(QFont("Microsoft YaHei UI", 9, QFont.Weight.DemiBold))
        p.drawText(QRectF(28, 0, w - 32, h),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)


class PowerButton(QWidget):
    """The big circular start/stop control."""

    clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._running = False
        self._busy = False
        self._busy_text = "正在启动…"
        self._hover = False
        self._pressed = False
        self._angle = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self.setFixedSize(178, 178)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip("开始 / 停止推流")

    # ------------------------------------------------------------------ state
    def set_running(self, running: bool) -> None:
        if running == self._running:
            return
        self._running = running
        self._busy = False
        if running:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def set_busy(self, text: str = "正在启动…") -> None:
        self._busy = True
        self._busy_text = text
        self._timer.start()
        self.update()

    def set_idle(self) -> None:
        self._busy = False
        if not self._running:
            self._timer.stop()
        self.update()

    @property
    def running(self) -> bool:
        return self._running

    def _tick(self) -> None:
        self._angle = (self._angle + 3.2) % 360.0
        self.update()

    # ------------------------------------------------------------------ events
    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled() and not self._busy:
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(event.position().toPoint()) and self.isEnabled() and not self._busy:
                self.clicked.emit()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not self._busy:
                self.clicked.emit()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------- paint
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, 72.0
        enabled = self.isEnabled()

        accent = QColor(theme.MINT if self._running else theme.ACCENT)
        if not enabled:
            accent = QColor("#3C4B63")
        if self._hover and enabled:
            accent = accent.lighter(112)

        # Soft outer glow.
        glow_alpha = 0 if not enabled else (86 if self._running else (54 if self._hover else 38))
        if glow_alpha:
            glow = QRadialGradient(QPointF(cx, cy), 90)
            glow.setColorAt(0.55, _rgba(accent.name(), glow_alpha))
            glow.setColorAt(0.82, _rgba(accent.name(), int(glow_alpha * 0.35)))
            glow.setColorAt(1.0, _rgba(accent.name(), 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QPointF(cx, cy), 90, 90)

        ring = QRectF(cx - 70, cy - 70, 140, 140)

        # Base ring.
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#1A2A44"), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawEllipse(ring)

        if self._running or self._busy:
            grad = QConicalGradient(QPointF(cx, cy), -90)
            grad.setColorAt(0.0, accent)
            grad.setColorAt(0.45, QColor(theme.VIOLET))
            grad.setColorAt(0.75, QColor(theme.ACCENT))
            grad.setColorAt(1.0, accent)
            p.setPen(QPen(grad, 6.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(ring, int((90 + self._angle) * 16), int(-286 * 16))
            p.setPen(QPen(_rgba(accent.name(), 50), 2))
            p.drawEllipse(ring.adjusted(5, 5, -5, -5))
        else:
            grad = QConicalGradient(QPointF(cx, cy), 120)
            grad.setColorAt(0.0, _rgba(theme.ACCENT, 40))
            grad.setColorAt(0.35, _rgba(theme.ACCENT, 170))
            grad.setColorAt(0.65, _rgba(theme.VIOLET, 150))
            grad.setColorAt(1.0, _rgba(theme.ACCENT, 40))
            p.setPen(QPen(grad, 4.0 if self._hover else 2.6,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(ring.adjusted(2, 2, -2, -2), 100 * 16, 320 * 16)

        # Inner disc.
        disc = QRectF(cx - 57, cy - 57, 114, 114)
        inner = QRadialGradient(QPointF(cx, cy - 20), 88)
        inner.setColorAt(0.0, QColor("#1A2A47"))
        inner.setColorAt(0.55, QColor("#111D31"))
        inner.setColorAt(1.0, QColor("#0A111E"))
        p.setPen(QPen(QColor("#263A5B"), 1.4))
        p.setBrush(inner)
        p.drawEllipse(disc)

        # Glass highlight.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_rgba("#FFFFFF", 10))
        p.drawEllipse(QRectF(cx - 43, cy - 49, 86, 22))

        # Power glyph.
        glyph = QColor("#F2F7FF") if enabled else QColor("#5A6B85")
        if self._running:
            glyph = QColor(theme.MINT)
        p.setPen(QPen(glyph, 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(cx - 15, cy - 32, 30, 30), 112 * 16, 316 * 16)
        p.drawLine(QPointF(cx, cy - 26), QPointF(cx, cy - 12))

        # Labels inside the disc.
        title = "停止推流" if self._running else ("正在启动…" if self._busy else "开始推流")
        if self._busy:
            title = self._busy_text
        sub = "STREAMING" if self._running else ("PLEASE WAIT" if self._busy else "READY")
        if not enabled:
            sub = "NO DEVICE"

        p.setPen(QColor(theme.TEXT if enabled else "#596A84"))
        p.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.DemiBold))
        p.drawText(QRectF(0, 90, w, 20),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, title)
        p.setPen(QColor(theme.DIM if enabled else "#40506A"))
        f = QFont("Segoe UI", 6, QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.3)
        p.setFont(f)
        p.drawText(QRectF(0, 109, w, 14),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, sub)


class WaveformWidget(QWidget):
    """Smoothed 52-bar live level meter."""

    BARS = 52

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._target: deque[float] = deque(maxlen=self.BARS)
        self._display: List[float] = [0.0] * self.BARS
        self._running = False
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(66)

    def set_running(self, running: bool) -> None:
        self._running = running
        self.update()

    def set_level(self, level: float) -> None:
        self._target.append(max(0.0, min(1.0, float(level))))

    def _tick(self) -> None:
        vals = list(self._target)
        if len(vals) < self.BARS:
            vals = [0.0] * (self.BARS - len(vals)) + vals
        else:
            vals = vals[-self.BARS:]
        changed = False
        for i in range(self.BARS):
            target = vals[i] if self._running else 0.0
            cur = self._display[i]
            nxt = cur + (target - cur) * 0.42
            if abs(nxt - cur) > 0.001:
                changed = True
            self._display[i] = nxt
        if changed or self._running:
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        bg = QRectF(0.5, 0.5, w - 1, h - 1)
        p.setPen(QPen(QColor(theme.BORDER_SOFT), 1))
        p.setBrush(QColor("#08111F"))
        p.drawRoundedRect(bg, 12, 12)

        left, right = 16.0, w - 16.0
        baseline = h - 12.0
        max_h = h - 26.0
        step = (right - left) / self.BARS
        bw = max(2.2, step * 0.52)

        active = QColor(theme.ACCENT)
        cool = QColor(theme.VIOLET)
        for i, v in enumerate(self._display):
            if not self._running and v < 0.01:
                continue
            x = left + i * step + (step - bw) / 2
            hh = 3.0 + max(0.0, v) * max_h
            t = i / max(1, self.BARS - 1)
            col = QColor(
                int(active.red() + (cool.red() - active.red()) * t),
                int(active.green() + (cool.green() - active.green()) * t),
                int(active.blue() + (cool.blue() - active.blue()) * t),
            )
            col.setAlpha(230)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(x, baseline - hh, bw, hh), bw / 2, bw / 2)
            p.setBrush(_rgba(col.name(), 26))
            p.drawRoundedRect(QRectF(x, baseline + 3, bw, min(6.0, hh * 0.12)), bw / 2, bw / 2)

        if not self._running:
            p.setPen(QPen(QColor("#1B2B44"), 1))
            p.drawLine(QPointF(left, baseline + 1), QPointF(right, baseline + 1))
            p.setPen(QColor(theme.DIM))
            p.setFont(QFont("Microsoft YaHei UI", 9))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       "开始推流后显示实时电平")


class MetricCard(QFrame):
    def __init__(self, label: str, value: str = "—", sub: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("SubCard")
        self.setFixedHeight(66)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(13, 8, 13, 7)
        lay.setSpacing(0)
        self._label = QLabel(label)
        self._label.setObjectName("MetricLabel")
        self._value = QLabel(value)
        self._value.setObjectName("MetricValue")
        self._sub = QLabel(sub)
        self._sub.setObjectName("MetricSub")
        lay.addWidget(self._label)
        lay.addWidget(self._value)
        lay.addWidget(self._sub)

    def set_value(self, value: str, sub: Optional[str] = None) -> None:
        self._value.setText(value)
        if sub is not None:
            self._sub.setText(sub)


class ClientListWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._clients: List[dict] = []
        self.setFixedHeight(86)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_clients(self, clients: Sequence[dict]) -> None:
        self._clients = list(clients)
        self.update()

    @staticmethod
    def _duration(sec: float) -> str:
        sec = int(max(0, sec))
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        if not self._clients:
            rect = QRectF(0.5, 0.5, w - 1, h - 1)
            p.setPen(QPen(QColor("#1A2B46"), 1, Qt.PenStyle.DashLine))
            p.setBrush(QColor("#08111F"))
            p.drawRoundedRect(rect, 10, 10)
            p.setPen(QColor(theme.DIM))
            p.setFont(QFont("Microsoft YaHei UI", 9))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "等待手机连接…")
            return

        rows = self._clients[:3]
        row_h, gap = 26, 4
        for i, c in enumerate(rows):
            y = i * (row_h + gap)
            rect = QRectF(0.5, y + 0.5, w - 1, row_h)
            p.setPen(QPen(QColor("#15243B"), 1))
            p.setBrush(QColor("#091322"))
            p.drawRoundedRect(rect, 8, 8)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.MINT))
            p.drawEllipse(QPointF(15, y + row_h / 2), 3.2, 3.2)

            p.setPen(QColor("#D5E2F4"))
            p.setFont(QFont("Consolas", 9))
            p.drawText(QRectF(27, y, w - 170, row_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       f"{c.get('ip', '')}:{c.get('port', '')}")

            meta = f"{self._duration(c.get('connected', 0))}   {int(c.get('packets', 0)):,} 包"
            p.setPen(QColor(theme.MUTED))
            p.setFont(QFont("Microsoft YaHei UI", 8))
            p.drawText(QRectF(w - 180, y, 166, row_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, meta)

        if len(self._clients) > len(rows):
            p.setPen(QColor(theme.MUTED))
            p.setFont(QFont("Microsoft YaHei UI", 8))
            p.drawText(QRectF(0, h - 14, w, 12), Qt.AlignmentFlag.AlignRight,
                       f"+{len(self._clients) - len(rows)} 台其他设备")


class LogView(QPlainTextEdit):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(500)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont("Cascadia Mono", 9))
        self.setPlaceholderText("运行日志会显示在这里")

    def append_line(self, msg: str) -> None:
        self.appendPlainText(f"{time.strftime('%H:%M:%S')}   {msg}")
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
