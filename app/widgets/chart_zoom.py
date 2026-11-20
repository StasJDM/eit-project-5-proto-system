"""Touch-friendly magnified view shared by every chart widget."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QScroller,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..i18n import i18n, t
from ..styles import C, FONT_BASE, FONT_VALUE


_CONTROL_STYLE = f"""
    QPushButton {{
        min-width: 64px; min-height: 52px;
        background: {C['bg_card']}; color: {C['text']};
        border: 1px solid {C['blue_light']}; border-radius: 8px;
        font-size: {FONT_VALUE}px; font-weight: bold; padding: 0 12px;
    }}
    QPushButton:pressed {{ background: {C['blue_dark']}; }}
    QPushButton:disabled {{ color: {C['text_dim']}; border-color: {C['border']}; }}
"""


class _ChartZoomOverlay(QFrame):
    """Window-sized live chart copy with zoom and touch panning."""

    def __init__(self, source: QWidget, controller: "ChartZoomController") -> None:
        window = source.window()
        super().__init__(window)
        self._source = source
        self._controller = controller
        # 100% means "fit the complete chart into the viewport".  Starting
        # from a hard-coded 150% cropped large chart panels immediately and
        # made the result look like a broken layout.
        self._zoom = 1.0
        window.installEventFilter(self)
        self.setObjectName("chart_zoom_overlay")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet(
            f"QFrame#chart_zoom_overlay {{ background:{C['bg_main']};"
            f"border:2px solid {C['blue_light']}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        toolbar = QWidget(self)
        toolbar.setFixedHeight(60)
        tools = QHBoxLayout(toolbar)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(10)

        self._title = QLabel()
        self._title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._title.setStyleSheet(
            f"color:{C['text']};font-size:{FONT_VALUE}px;font-weight:bold;"
        )
        tools.addWidget(self._title, stretch=1)

        self._minus = QPushButton("−")
        self._percent = QLabel()
        self._percent.setFixedWidth(90)
        self._percent.setAlignment(Qt.AlignCenter)
        self._percent.setStyleSheet(
            f"color:{C['text']};font-size:{FONT_BASE}px;font-weight:bold;"
        )
        self._plus = QPushButton("+")
        self._reset = QPushButton()
        self._close = QPushButton("×")
        for button in (self._minus, self._plus, self._reset, self._close):
            button.setStyleSheet(_CONTROL_STYLE)
            tools.addWidget(button)
        tools.insertWidget(2, self._percent)
        root.addWidget(toolbar)

        self._image = QLabel()
        self._image.setAlignment(Qt.AlignCenter)
        self._image.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignCenter)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setWidget(self._image)
        self._scroll.setStyleSheet(f"background:{C['bg_wave']};")
        QScroller.grabGesture(
            self._scroll.viewport(), QScroller.TouchGesture
        )
        root.addWidget(self._scroll, stretch=1)

        self._minus.clicked.connect(lambda: self._change_zoom(-0.25))
        self._plus.clicked.connect(lambda: self._change_zoom(0.25))
        self._reset.clicked.connect(self._reset_zoom)
        self._close.clicked.connect(self.close)
        i18n.language_changed.connect(self.retranslate)

        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self.retranslate()
        self._refresh()

    @property
    def zoom_factor(self) -> float:
        return self._zoom

    def retranslate(self, *_args) -> None:
        self._title.setText(t("chart_zoom_title"))
        self._minus.setToolTip(t("chart_zoom_out"))
        self._minus.setAccessibleName(t("chart_zoom_out"))
        self._plus.setToolTip(t("chart_zoom_in"))
        self._plus.setAccessibleName(t("chart_zoom_in"))
        self._reset.setText(t("chart_zoom_reset"))
        self._reset.setToolTip(t("chart_zoom_reset"))
        self._reset.setAccessibleName(t("chart_zoom_reset"))
        self._close.setToolTip(t("chart_zoom_close"))
        self._close.setAccessibleName(t("chart_zoom_close"))
        self._update_controls()

    def _change_zoom(self, delta: float) -> None:
        self._set_zoom(self._zoom + delta)

    def _reset_zoom(self) -> None:
        self._set_zoom(1.0)

    def _set_zoom(self, value: float) -> None:
        self._zoom = max(1.0, min(4.0, round(value, 2)))
        self._update_controls()
        self._refresh()

    def _update_controls(self) -> None:
        self._percent.setText(f"{round(self._zoom * 100):d}%")
        self._minus.setEnabled(self._zoom > 1.0)
        self._plus.setEnabled(self._zoom < 4.0)

    def _refresh(self) -> None:
        if not self._source or not self._source.isVisible():
            return
        button = self._controller.button
        button_was_visible = button.isVisible()
        button.hide()
        pixmap = self._source.grab()
        if button_was_visible:
            button.show()
            button.raise_()
        if pixmap.isNull():
            return
        viewport = self._scroll.viewport().size()
        fit = min(
            max(1, viewport.width() - 4) / max(1, pixmap.width()),
            max(1, viewport.height() - 4) / max(1, pixmap.height()),
        )
        target = QSize(
            max(1, round(pixmap.width() * fit * self._zoom)),
            max(1, round(pixmap.height() * fit * self._zoom)),
        )
        scaled = pixmap.scaled(
            target, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self._image.setPixmap(scaled)
        self._image.setFixedSize(scaled.size())

    def showEvent(self, event) -> None:  # noqa: N802
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        QTimer.singleShot(0, self._refresh)
        super().showEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.parentWidget() and event.type() == QEvent.Resize:
            self.setGeometry(watched.rect())
        return False

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        parent = self.parentWidget()
        if parent is not None:
            parent.removeEventFilter(self)
        self._controller.overlay = None
        super().closeEvent(event)


class ChartZoomController(QObject):
    """Adds a persistent magnifier affordance to one chart container."""

    BUTTON_SIZE = 46
    MARGIN = 6

    def __init__(self, chart: QWidget) -> None:
        super().__init__(chart)
        self.chart = chart
        self.overlay: _ChartZoomOverlay | None = None
        self.button = QPushButton("🔍", chart)
        self.button.setObjectName("chart_magnifier_button")
        self.button.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setStyleSheet(f"""
            QPushButton#chart_magnifier_button {{
                background: rgba(13, 17, 23, 210); color: {C['text']};
                border: 2px solid {C['blue_light']}; border-radius: 23px;
                font-size: 22px; padding: 0;
            }}
            QPushButton#chart_magnifier_button:pressed {{
                background: {C['blue_dark']};
            }}
        """)
        self.button.clicked.connect(self.open)
        chart.installEventFilter(self)
        i18n.language_changed.connect(self.retranslate)
        self.retranslate()
        self._position_button()
        self.button.show()
        self.button.raise_()

    def retranslate(self, *_args) -> None:
        label = t("chart_magnifier")
        self.button.setToolTip(label)
        self.button.setAccessibleName(label)

    def open(self) -> None:
        if self.overlay is not None:
            self.overlay.raise_()
            return
        self.overlay = _ChartZoomOverlay(self.chart, self)
        self.overlay.show()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        chart = getattr(self, "chart", None)
        if watched is chart and event.type() in {
            QEvent.Resize,
            QEvent.Show,
        }:
            self._position_button()
        return False

    def _position_button(self) -> None:
        chart = getattr(self, "chart", None)
        button = getattr(self, "button", None)
        if chart is None or button is None:
            return
        x = max(self.MARGIN, chart.width() - self.BUTTON_SIZE - self.MARGIN)
        y = max(0, min(self.MARGIN, chart.height() - self.BUTTON_SIZE))
        button.move(QPoint(x, y))
        button.raise_()


def attach_chart_zoom(chart: QWidget) -> ChartZoomController:
    """Attach the shared zoom UI once and retain it for the chart lifetime."""
    existing = getattr(chart, "_chart_zoom_controller", None)
    if existing is not None:
        return existing
    controller = ChartZoomController(chart)
    chart._chart_zoom_controller = controller
    return controller
