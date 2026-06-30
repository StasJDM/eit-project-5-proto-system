"""Animated lung cross-section visualisation.

Supports runtime language switching via i18n.language_changed.
"""

import math
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from ..styles import C, SECTION_COLORS
from ..i18n import t, i18n


class LungVizWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 240)
        self._phase    = 0.0
        self._roi_vals = [0.5] * 8
        i18n.language_changed.connect(lambda _: self.update())

    # ── Public ───────────────────────────────────────────────────────────────

    def update_state(self, phase: float, roi_vals: list):
        self._phase    = max(0.0, min(1.0, phase))
        self._roi_vals = list(roi_vals)
        self.update()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(C["bg_panel"]))

        # Title
        p.setPen(QColor(C["text_dim"]))
        p.setFont(QFont("Arial", 20, QFont.Bold))
        p.drawText(0, 2, w, 30, Qt.AlignCenter, t("lung_breath_cycle"))

        top_y = 34
        p.setFont(QFont("Arial", 16, QFont.Bold))
        p.setPen(QColor(SECTION_COLORS["R"]))
        p.drawText(int(w * 0.18), top_y, 24, 20, Qt.AlignCenter, "R")
        p.setPen(QColor(SECTION_COLORS["L"]))
        p.drawText(int(w * 0.62), top_y, 24, 20, Qt.AlignCenter, "L")

        cx   = w // 2
        cy   = h // 2 + 10
        tx_w = int(w * 0.76)
        tx_h = int(h * 0.62)
        scale = 1.0 + 0.12 * self._phase

        # Thorax
        p.setPen(QPen(QColor(C["border_light"]), 2))
        p.setBrush(QBrush(QColor(C["thorax"])))
        p.drawEllipse(QRectF(cx - tx_w / 2, cy - tx_h / 2, tx_w, tx_h))

        # Spine marker
        p.setPen(QColor(C["text_lo"]))
        p.setFont(QFont("Arial", 14))
        p.drawText(cx - 6, int(cy + tx_h / 2) - 14, 12, 16, Qt.AlignCenter, "▼")

        # Right lung
        rl_cx = cx - int(tx_w * 0.24)
        rl_w  = int(tx_w * 0.31 * scale)
        rl_h  = int(tx_h * 0.74 * scale)
        r_vent = sum(self._roi_vals[:4]) / 4.0
        p.setPen(QPen(QColor(C["border_light"]), 1))
        p.setBrush(QBrush(self._lung_color(r_vent, "right")))
        p.drawEllipse(QRectF(rl_cx - rl_w / 2, cy - rl_h / 2, rl_w, rl_h))

        # Left lung
        ll_cx = cx + int(tx_w * 0.23)
        ll_w  = int(tx_w * 0.28 * scale)
        ll_h  = int(tx_h * 0.70 * scale)
        l_vent = sum(self._roi_vals[4:]) / 4.0
        p.setBrush(QBrush(self._lung_color(l_vent, "left")))
        p.drawEllipse(QRectF(ll_cx - ll_w / 2, cy - ll_h / 2, ll_w, ll_h))

        # Electrode dots
        p.setPen(QPen(QColor("#40c4ff"), 1))
        p.setBrush(QBrush(QColor("#40c4ff")))
        for i in range(16):
            angle = 2 * math.pi * i / 16 - math.pi / 2
            ex = cx + (tx_w / 2) * math.cos(angle)
            ey = cy + (tx_h / 2) * math.sin(angle)
            p.drawEllipse(QRectF(ex - 2.5, ey - 2.5, 5, 5))

        self._draw_roi_labels(p, cx, cy, tx_w, tx_h)

        # Bed surface — visible posterior marker so orientation is unambiguous
        bar_px = 12
        bar_y  = h - bar_px - 4
        bm     = int(w * 0.04)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#3d5a72")))
        p.drawRect(bm, bar_y, w - 2 * bm, bar_px)

    def _lung_color(self, vent: float, side: str) -> QColor:
        """Бежево-серая карта: правое — тёплый песок, левое — холодный серо-беж."""
        lvl = max(0.0, min(1.0, vent + 0.3 * self._phase))
        if side == "right":
            # тёплый беж: от тёмного какао до светлого песка
            r = int(88 + lvl * 142)
            g = int(78 + lvl * 128)
            b = int(62 + lvl * 98)
        else:
            # холодный серо-беж: от графита до жемчужного
            r = int(76 + lvl * 138)
            g = int(80 + lvl * 132)
            b = int(78 + lvl * 128)
        return QColor(r, g, b, 220)

    def _draw_roi_labels(self, p, cx, cy, tw, th):
        w = self.width()
        p.setFont(QFont("Arial", 13))
        p.setPen(QColor(C["text_dim"]))
        step = th / 5
        left_x = 4
        right_x = w - 58
        for i, name in enumerate(["ROI_1", "ROI_2", "ROI_3", "ROI_4"]):
            y = int(cy - th / 2 + step * (i + 0.6))
            p.drawText(left_x, y, 54, 20, Qt.AlignLeft | Qt.AlignVCenter, name)
        for i, name in enumerate(["ROI_5", "ROI_6", "ROI_7", "ROI_8"]):
            y = int(cy - th / 2 + step * (i + 0.6))
            p.drawText(right_x, y, 54, 20, Qt.AlignRight | Qt.AlignVCenter, name)
