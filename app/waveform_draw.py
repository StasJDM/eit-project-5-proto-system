"""Shared QPainter helpers for filled waveform traces."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QBrush


def draw_filled_waveform(
    painter: QPainter,
    xs: list[float],
    ys: list[float],
    color: QColor,
    baseline_y: float,
    line_width: float = 1.5,
    fill_alpha: int = 55,
) -> None:
    """Draw a waveform line with semi-transparent fill down to *baseline_y*."""
    if len(xs) < 2:
        return

    line = QPainterPath()
    line.moveTo(xs[0], ys[0])
    for x, y in zip(xs[1:], ys[1:]):
        line.lineTo(x, y)

    fill = QPainterPath(line)
    fill.lineTo(xs[-1], baseline_y)
    fill.lineTo(xs[0], baseline_y)
    fill.closeSubpath()

    fc = QColor(color)
    fc.setAlpha(fill_alpha)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(fc))
    painter.drawPath(fill)

    pen = QPen(color, line_width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(line)
