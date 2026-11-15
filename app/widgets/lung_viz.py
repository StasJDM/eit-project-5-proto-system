"""Native Qt rendering of reconstructed EIT cross-sections.

Every value in ``reconstructed_delta_z`` is painted as its own grid cell. The
widget uses QPainter rather than a plotting library so it stays lightweight and
visually consistent with the monitor UI.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..i18n import i18n, t
from ..color_maps import DEFAULT_COLOR_MAP_ID, resolve_color_map
from ..styles import C


class LungVizWidget(QWidget):
    """Discrete heat map shown in direct patient orientation (L left, R right)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(150, 150)
        self._phase = 0.0
        self._roi_vals: tuple[float, ...] = (0.0,) * 8
        self._delta_reconstruction: tuple[tuple[float, ...], ...] | None = None
        self._absolute_conductivity: tuple[tuple[float, ...], ...] | None = None
        self._display_mode = "absolute"
        self._color_limit: float | None = None
        self._two_color_visualization = True
        self._color_map_id = DEFAULT_COLOR_MAP_ID
        self._custom_color_low = "#29b6d1"
        self._custom_color_high = "#ffc857"
        self._rendered_element_count = 0
        self.setToolTip(t("lung_reconstruction_tooltip"))
        i18n.language_changed.connect(self._on_language_changed)

    @property
    def reconstruction_shape(self) -> tuple[int, int] | None:
        reconstruction = self._displayed_map()
        if reconstruction is None:
            return None
        return len(reconstruction), len(reconstruction[0])

    @property
    def display_mode(self) -> str:
        return self._effective_display_mode()

    @property
    def delta_color_limit(self) -> float | None:
        return self._color_limit

    @property
    def patient_left_is_screen_left(self) -> bool:
        return True

    @property
    def rendered_element_count(self) -> int:
        """Number of finite elements painted during the most recent render."""
        return self._rendered_element_count

    @property
    def roi_grid_labels(self) -> tuple[tuple[str, str], ...]:
        """ROI labels in screen order: patient left, then patient right."""
        roi_count = len(self._roi_vals)
        if roi_count < 2 or roi_count % 2:
            return ()
        bands = roi_count // 2
        return tuple(
            (f"ROI_{bands + row + 1}", f"ROI_{row + 1}")
            for row in range(bands)
        )

    def _on_language_changed(self, _language: str) -> None:
        self.setToolTip(t("lung_reconstruction_tooltip"))
        self.update()

    @property
    def color_map_id(self) -> str:
        return self._color_map_id

    @property
    def two_color_visualization(self) -> bool:
        return self._two_color_visualization

    def set_color_settings(
        self,
        *,
        two_color: bool,
        color_map_id: str,
        custom_low: str = "#29b6d1",
        custom_high: str = "#ffc857",
    ) -> None:
        """Apply persisted colour preferences without changing map data."""
        self._two_color_visualization = bool(two_color)
        self._color_map_id = color_map_id
        self._custom_color_low = custom_low
        self._custom_color_high = custom_high
        self.update()

    def update_state(
        self,
        phase: float | None,
        roi_vals: Sequence[float | None],
        reconstruction_map: Sequence[Sequence[float]] | None = None,
        absolute_conductivity_map: Sequence[Sequence[float]] | None = None,
    ) -> None:
        self._phase = max(0.0, min(1.0, phase)) if phase is not None else 0.0
        self._roi_vals = tuple(
            float(value) if value is not None else 0.0 for value in roi_vals
        )
        self._delta_reconstruction = self._validated_map(reconstruction_map)
        self._absolute_conductivity = self._validated_map(absolute_conductivity_map)
        if self._delta_reconstruction is None and self._absolute_conductivity is None:
            self._color_limit = None
        if self._delta_reconstruction is not None:
            frame_limit = max(
                abs(value) for row in self._delta_reconstruction for value in row
            )
            if self._color_limit is None and frame_limit > 1e-9:
                self._color_limit = frame_limit
        self.update()

    def _effective_display_mode(self) -> str:
        if self._display_mode == "absolute" and self._absolute_conductivity is not None:
            return "absolute"
        return "delta"

    def _displayed_map(self) -> tuple[tuple[float, ...], ...] | None:
        if self._effective_display_mode() == "absolute":
            return self._absolute_conductivity
        return self._delta_reconstruction

    def mouseReleaseEvent(self, event) -> None:
        if (
            event.button() == Qt.LeftButton
            and self._delta_reconstruction is not None
            and self._absolute_conductivity is not None
        ):
            self._display_mode = "delta" if self._display_mode == "absolute" else "absolute"
            self.update()
        super().mouseReleaseEvent(event)

    @staticmethod
    def _validated_map(
        values: Sequence[Sequence[float]] | None,
    ) -> tuple[tuple[float, ...], ...] | None:
        if values is None:
            return None
        try:
            result = tuple(tuple(float(value) for value in row) for row in values)
        except (TypeError, ValueError):
            return None
        if not result or not result[0]:
            return None
        width = len(result[0])
        if any(len(row) != width for row in result):
            return None
        if any(not math.isfinite(value) for row in result for value in row):
            return None
        return result

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(C["bg_panel"]))

        compact = self.width() < 190 or self.height() < 190
        title_h = 22 if compact else 30
        bottom_h = 19 if compact else 27
        roi_label_gutter = 42 if compact else 54
        roi_line_extension = 7 if compact else 10
        outer_side_margin = 4 if compact else 8

        painter.setPen(QColor(C["text_dim"]))
        painter.setFont(QFont("Arial", 10 if compact else 13, QFont.Bold))
        painter.drawText(
            0, 0, self.width(), title_h,
            Qt.AlignCenter,
            t(
                "lung_absolute_conductivity_map"
                if self._effective_display_mode() == "absolute"
                else "lung_reconstruction_map"
            ),
        )

        available_h = max(1, self.height() - title_h - bottom_h)
        side_reserve = roi_label_gutter + roi_line_extension + outer_side_margin
        map_size = max(1, min(self.width() - 2 * side_reserve, available_h))
        map_left = (self.width() - map_size) // 2
        map_top = title_h + (available_h - map_size) // 2
        map_rect = QRectF(map_left, map_top, map_size, map_size)

        painter.setPen(QPen(QColor(C["border"]), 1))
        painter.setBrush(QColor(C["bg_card"]))
        painter.drawRoundedRect(map_rect.adjusted(-3, -3, 3, 3), 7, 7)

        self._draw_map(painter, map_rect)
        self._draw_roi_grid(
            painter,
            map_rect,
            compact,
            label_gutter=roi_label_gutter,
            line_extension=roi_line_extension,
        )
        self._draw_orientation(painter, map_rect, compact)
        self._draw_legend(painter, map_rect, compact)

    def _draw_map(self, painter: QPainter, rect: QRectF) -> None:
        self._rendered_element_count = 0
        reconstruction = self._displayed_map()
        if reconstruction is None:
            painter.setPen(QColor(C["text_lo"]))
            painter.setFont(QFont("Arial", 9))
            symbol = "σ rel.\n—" if self._effective_display_mode() == "absolute" else "ΔZ\n—"
            painter.drawText(rect, Qt.AlignCenter, symbol)
            return

        rows = len(reconstruction)
        columns = len(reconstruction[0])
        cell_w = rect.width() / columns
        cell_h = rect.height() / rows
        grid_pen = QPen(QColor(255, 255, 255, 18), 0.45)

        # Pixel cells stay crisp; antialiasing is restored for contours.
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(grid_pen)
        for row_index, row in enumerate(reconstruction):
            y0 = rect.top() + row_index * cell_h
            y1 = rect.top() + (row_index + 1) * cell_h
            for column_index, value in enumerate(row):
                # Reconstruction coordinates use the radiological convention.
                # Mirror only the presentation so the patient's left side is
                # also on the left side of the operator's screen.
                display_column = columns - 1 - column_index
                x0 = rect.left() + display_column * cell_w
                x1 = rect.left() + (display_column + 1) * cell_w
                painter.setBrush(self._element_color(value))
                painter.drawRect(QRectF(x0, y0, x1 - x0, y1 - y0))
                self._rendered_element_count += 1
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Landmarks are overlays; they never replace or aggregate map cells.
        thorax = QPainterPath()
        thorax.addEllipse(rect.adjusted(
            rect.width() * 0.04, rect.height() * 0.09,
            -rect.width() * 0.04, -rect.height() * 0.09,
        ))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(185, 211, 225, 145), 1.2))
        painter.drawPath(thorax)
        painter.setPen(QPen(QColor(185, 211, 225, 85), 0.8, Qt.DashLine))
        painter.drawLine(
            rect.center().x(), rect.top() + rect.height() * 0.13,
            rect.center().x(), rect.bottom() - rect.height() * 0.13,
        )

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#40c4ff"))
        cx, cy = rect.center().x(), rect.center().y()
        radius_x, radius_y = rect.width() * 0.48, rect.height() * 0.41
        dot = max(1.4, rect.width() * 0.012)
        for index in range(16):
            angle = 2 * math.pi * index / 16 - math.pi / 2
            x = cx + radius_x * math.cos(angle)
            y = cy + radius_y * math.sin(angle)
            painter.drawEllipse(QRectF(x - dot, y - dot, dot * 2, dot * 2))

    def _draw_roi_grid(
        self,
        painter: QPainter,
        rect: QRectF,
        compact: bool,
        *,
        label_gutter: float,
        line_extension: float,
    ) -> None:
        """Draw rectangular ROIs across the complete reconstruction area."""
        labels = self.roi_grid_labels
        if not labels:
            return

        rows = len(labels)
        cell_h = rect.height() / rows

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(238, 247, 252, 205), 1.25))
        painter.drawLine(rect.left(), rect.top(), rect.left(), rect.bottom())
        painter.drawLine(rect.center().x(), rect.top(), rect.center().x(), rect.bottom())
        painter.drawLine(rect.right(), rect.top(), rect.right(), rect.bottom())
        for row in range(rows + 1):
            y = rect.top() + row * cell_h
            painter.drawLine(
                rect.left() - line_extension,
                y,
                rect.right() + line_extension,
                y,
            )

        font_size = max(6, min(9 if compact else 11, int(cell_h * 0.34)))
        painter.setFont(QFont("Arial", font_size, QFont.Bold))
        label_padding = 3.0
        for row, row_labels in enumerate(labels):
            for column, label in enumerate(row_labels):
                if column == 0:
                    cell = QRectF(
                        rect.left() - line_extension - label_gutter - 3.0,
                        rect.top() + row * cell_h,
                        label_gutter,
                        cell_h,
                    )
                    alignment = Qt.AlignRight | Qt.AlignVCenter
                else:
                    cell = QRectF(
                        rect.right() + line_extension + 3.0,
                        rect.top() + row * cell_h,
                        label_gutter,
                        cell_h,
                    )
                    alignment = Qt.AlignLeft | Qt.AlignVCenter
                bounds = painter.boundingRect(cell, alignment, label)
                background = bounds.adjusted(
                    -label_padding, -1.0, label_padding, 1.0
                ).intersected(cell.adjusted(1.0, 1.0, -1.0, -1.0))
                painter.fillRect(background, QColor(8, 18, 26, 165))
                painter.setPen(QColor(248, 252, 255, 235))
                painter.drawText(cell, alignment, label)
        painter.restore()

    def _element_color(self, value: float) -> QColor:
        low_hex, high_hex = resolve_color_map(
            self._color_map_id,
            self._custom_color_low,
            self._custom_color_high,
        )
        low_color = QColor(low_hex)
        high_color = QColor(high_hex)
        neutral = QColor("#17232d")
        if self._effective_display_mode() == "absolute":
            if value <= 0.0:
                return QColor("#101820")
            level = max(-1.5, min(1.5, math.log(value))) / 3.0 + 0.5
            if not self._two_color_visualization:
                return self._mix(neutral, high_color, level)
            if level < 0.5:
                return self._mix(low_color, neutral, level * 2.0)
            return self._mix(neutral, high_color, (level - 0.5) * 2.0)
        level = max(-1.0, min(1.0, value / max(self._color_limit or 0.0, 1e-9)))
        if not self._two_color_visualization:
            return self._mix(neutral, high_color, abs(level))
        if level < 0.0:
            return self._mix(neutral, low_color, abs(level))
        return self._mix(neutral, high_color, level)

    @staticmethod
    def _mix(low: QColor, high: QColor, amount: float) -> QColor:
        amount = max(0.0, min(1.0, amount))
        return QColor(
            round(low.red() + (high.red() - low.red()) * amount),
            round(low.green() + (high.green() - low.green()) * amount),
            round(low.blue() + (high.blue() - low.blue()) * amount),
        )

    def _draw_orientation(self, painter: QPainter, rect: QRectF, compact: bool) -> None:
        painter.setFont(QFont("Arial", 8 if compact else 10, QFont.Bold))
        painter.setPen(QColor(C["text_dim"]))
        painter.drawText(QRectF(rect.left() - 20, rect.top(), 18, 18), Qt.AlignCenter, "L")
        painter.drawText(QRectF(rect.right() + 2, rect.top(), 18, 18), Qt.AlignCenter, "R")
        painter.setFont(QFont("Arial", 7 if compact else 9))
        painter.drawText(
            QRectF(rect.left(), rect.top() - 16, rect.width(), 14), Qt.AlignCenter, "V"
        )
        painter.drawText(
            QRectF(rect.left(), rect.bottom() + 2, rect.width(), 14), Qt.AlignCenter, "D"
        )

    def _draw_legend(self, painter: QPainter, rect: QRectF, compact: bool) -> None:
        legend_w = min(rect.width() * 0.62, 150.0)
        legend_h = 5.0 if compact else 7.0
        legend_x = rect.center().x() - legend_w / 2
        legend_y = self.height() - (10 if compact else 16)
        steps = max(12, int(legend_w))
        painter.setPen(Qt.NoPen)
        for index in range(steps):
            fraction = index / max(steps - 1, 1)
            if self._effective_display_mode() == "absolute":
                value = math.exp(-1.5 + 3.0 * fraction)
            else:
                value = (-1.0 + 2.0 * fraction) * (self._color_limit or 1e-9)
            painter.setBrush(self._element_color(value))
            painter.drawRect(QRectF(
                legend_x + legend_w * index / steps,
                legend_y,
                legend_w / steps + 0.5,
                legend_h,
            ))
        painter.setPen(QColor(C["text_lo"]))
        painter.setFont(QFont("Arial", 7 if compact else 8))
        left_label = "σ−" if self._effective_display_mode() == "absolute" else "−"
        right_label = "σ+" if self._effective_display_mode() == "absolute" else "+"
        painter.drawText(QRectF(legend_x - 24, legend_y - 5, 22, 14), Qt.AlignRight, left_label)
        painter.drawText(
            QRectF(legend_x + legend_w + 2, legend_y - 5, 22, 14), Qt.AlignLeft, right_label
        )
