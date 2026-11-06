"""Окно АНАЛИЗ — три вкладки.

  Вкладка 1 — Тип патологического дыхания   (PCA-анализ + классификатор)
  Вкладка 2 — Аэрация РЕГИОНАРНАЯ           (9 каналов осциллограмм)
  Вкладка 3 — Аэрация ГЛОБАЛЬНАЯ            (визуализация лёгких + суммарная кривая)
"""

from datetime import timedelta

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QGridLayout, QStackedWidget, QScrollArea, QComboBox,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QCursor
from ..waveform_draw import draw_filled_waveform

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 — регистрирует проекцию '3d'

from ..application import (
    BreathingClass, BreathingClassificationService, BreathingModelVisualization,
    EventMarkerService, MonitoringData,
)
from ..domain import utc_now
from ..application.monitoring import DISPLAY_WINDOW_SEC, DISPLAY_SAMPLES, FS
from ..application.signal_shapes import breath_waveform
from ..session_timers import SessionTimers
from ..widgets.duration_counters import DurationCounter, _VALUE_FONT
from ..widgets.lung_viz import LungVizWidget
from ..widgets.waveform_panel import WaveformPanel, RegionalWaveformPanel
from ..styles import C, WAVE_COLORS, configure_event_marker_btn, EVENT_MARKER_BTN_HEIGHT, TAB_BAR_FONT, TAB_BAR_SUB_FONT, FONT_BASE, FONT_SMALL, FONT_LABEL, FONT_VALUE, FONT_BTN_START
from ..i18n import t, i18n
from ..ui_text import quality_reason_text, quality_text

PAINT_MS  = 100
RR_BPM = 15

_BT_KEYS = [
    "analysis_bt_eupnea",
    "analysis_bt_periodic",
    "analysis_bt_tachypnea",
    "analysis_bt_retraction",
    "analysis_bt_gasping",
    "analysis_bt_bradypnea",
    "analysis_bt_dyspnea",
    "analysis_bt_apnea_central",
    "analysis_bt_apnea_obstructive",
    "analysis_bt_apnea_mixed",
    "analysis_bt_apnea_reflex",
]
_BT_COLORS = [
    "#4caf50", "#009688", "#ff9800", "#ff5722", "#e91e63",
    "#00bcd4", "#ffc107", "#f44336", "#9c27b0", "#3f51b5", "#795548",
]

_BG  = C["bg_main"]   # "#0d1117"
_AX  = C["bg_wave"]   # "#080e14"
_TXT = C["text"]       # "#e8eaed"
_DIM = C["text_dim"]   # "#8b949e"
_BRD = C["border"]     # "#1e3a5f"


# ═══════════════════════════════════════════════════════════════════════════════
# Мелкие вспомогательные виджеты
# ═══════════════════════════════════════════════════════════════════════════════

class _WaveCvs(QWidget):
    """Однополосный прокручиваемый осциллограф."""

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._data = np.zeros(DISPLAY_SAMPLES)
        self._col  = QColor(color)
        self._bg   = QColor(C["bg_wave"])
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def set_data(self, arr: np.ndarray):
        self._data = arr
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, self._bg)
        d = self._data
        n = len(d)
        if n < 2:
            return
        mx, my = 2, 5
        pw, ph = w - 2 * mx, h - 2 * my
        lo, hi = float(d.min()), float(d.max())
        if hi - lo < 1e-9:
            hi = lo + 1.0
        xs, ys = [], []
        for i in range(n):
            x = mx + (i / (n - 1)) * pw
            y = my + (1.0 - (d[i] - lo) / (hi - lo)) * ph
            xs.append(x)
            ys.append(y)
        draw_filled_waveform(p, xs, ys, self._col, my + ph)


class _PBox(QFrame):
    """Именованный числовой индикатор: параметр слева, значение справа — одна рамка."""

    _W = 152
    _H = 58

    def __init__(self, label: str, w: int | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("param_box")
        self.setFixedSize(w if w is not None else self._W, self._H)
        self.setStyleSheet(f"""
            QFrame#param_box {{
                background-color: {C['bg_card']};
                border: 1px solid {C['border']};
                border-radius: 4px;
            }}
            QFrame#param_box QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(10)

        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        lbl.setStyleSheet(f"color:{C['text_dim']};font-size:{FONT_LABEL}px;")
        lay.addWidget(lbl)

        lay.addStretch()

        self._v = QLabel("—")
        self._v.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self._v.setMinimumWidth(56)
        self._v.setStyleSheet(
            f"color:{C['text']};font-size:{FONT_VALUE}px;font-weight:bold;"
        )
        lay.addWidget(self._v)

    def set_value(self, v):
        if v is None:
            self._v.setText("—")
        else:
            self._v.setText(f"{v:.1f}" if isinstance(v, float) else str(v))


def _hsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color:{C['border']};margin:2px 0;max-height:1px;")
    return f


class _EventMarkerButton(QPushButton):
    def __init__(self):
        super().__init__()
        configure_event_marker_btn(self)
        i18n.language_changed.connect(self.retranslate)
        self.retranslate()

    def retranslate(self, *_args):
        self.setText(t("wave_event_marker"))


def _make_event_btn() -> QPushButton:
    return _EventMarkerButton()


def _start_btn_text(running: bool) -> str:
    return t("btn_stop") if running else t("btn_start")


_START_STYLE_RUN = f"""
    QPushButton {{
        background:{C['alarm']}; color:white;
        border:1px solid #b71c1c; border-radius:4px;
        font-size:{FONT_BTN_START}px; font-weight:bold; padding:10px 20px;
    }}
    QPushButton:hover {{ background:#c62828; }}
"""


def _configure_start_btn(btn: QPushButton):
    btn.setObjectName("btn_start")
    btn.setFixedHeight(52)
    btn.setMinimumWidth(100)


class _BottomBar(QWidget):
    """Нижняя панель: кнопка Старт, счётчики, маркер событий."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(max(EVENT_MARKER_BTN_HEIGHT, _VALUE_FONT * 2) + 28)
        self.setStyleSheet(f"background:{C['bg_panel']};border-top:1px solid {C['border']};")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(10)

        self.btn_start = QPushButton(_start_btn_text(False))
        _configure_start_btn(self.btn_start)
        lay.addWidget(self.btn_start)

        self.cnt_eit = DurationCounter("param_eit_duration", stacked=True)
        self.cnt_es  = DurationCounter("param_es_time", stacked=True)
        counters = QWidget()
        counters.setStyleSheet("background:transparent;")
        cl = QGridLayout(counters)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setHorizontalSpacing(16)
        cl.setVerticalSpacing(4)
        cl.addWidget(self.cnt_eit, 0, 0)
        cl.addWidget(self.cnt_es,  0, 1)
        lay.addWidget(counters)

        lay.addStretch()

        self.btn_event = _make_event_btn()
        lay.addWidget(self.btn_event)

        i18n.language_changed.connect(self.retranslate)
        self.retranslate()

    def sync_start(self, running: bool):
        self.btn_start.setText(_start_btn_text(running))
        self.btn_start.setStyleSheet(_START_STYLE_RUN if running else "")

    def set_counters(self, eit: str, es: str):
        self.cnt_eit.set_value(eit)
        self.cnt_es.set_value(es)

    def retranslate(self):
        self.cnt_eit.retranslate()
        self.cnt_es.retranslate()


# ═══════════════════════════════════════════════════════════════════════════════
# Matplotlib фигуры (PCA-анализ)
# ═══════════════════════════════════════════════════════════════════════════════

def _ax_style(ax, title: str = ""):
    ax.set_facecolor(_AX)
    for sp in ax.spines.values():
        sp.set_color(_BRD)
    ax.tick_params(colors=_DIM, labelsize=6)
    if title:
        ax.set_title(title, fontsize=7, color=_TXT, pad=3)
    ax.xaxis.label.set_color(_DIM)
    ax.xaxis.label.set_fontsize(6)
    ax.yaxis.label.set_color(_DIM)
    ax.yaxis.label.set_fontsize(6)


def _build_pca_figure() -> Figure:
    """Создаёт 6-графичную фигуру PCA-анализа с мок-данными."""
    np.random.seed(42)
    n_types, n_pts = 11, 28

    centers = np.array([
        [-14.0,  4.0,  2.0], [ 9.0, 11.0, -1.0], [-7.0, -9.0,  4.0],
        [  4.0,-14.0, -2.0], [14.0, -7.0,  0.0], [-11.0, 11.0, -3.0],
        [ 17.0,  4.0,  1.0], [-4.0, 14.0,  5.0], [11.0,  -4.0, -1.0],
        [-14.0, -4.0,  3.0], [  1.0, 7.0, -4.0],
    ])
    variances = np.array([0.35, 0.22, 0.15, 0.10, 0.07, 0.04, 0.03, 0.02, 0.01, 0.008, 0.002])
    variances /= variances.sum()

    pts = np.vstack([centers[i] + np.random.randn(n_pts, 3) * 1.5 for i in range(n_types)])
    labels = np.repeat(range(n_types), n_pts)

    dist_mat = np.linalg.norm(centers[:, None] - centers[None, :], axis=-1)

    t_arr = np.linspace(0, DISPLAY_WINDOW_SEC, int(DISPLAY_WINDOW_SEC * FS))
    templates = []
    for i in range(n_types):
        amp  = 1.0 - i * 0.04
        if i == 3:
            sig = np.zeros_like(t_arr)
            sig[:60] = _mock_breath_trace(t_arr[:60], RR_BPM / 60.0, 0.5)
        elif i == 7:
            env = np.abs(np.sin(np.pi * t_arr / 30))
            sig = amp * env * _mock_breath_trace(t_arr, (RR_BPM / 60.0) * (0.9 + i * 0.04))
        else:
            freq = (RR_BPM / 60.0) * (0.85 + i * 0.04)
            sig = amp * _mock_breath_trace(t_arr, freq)
        templates.append(sig)

    names_short = ["Эупноэ", "Тахипн.", "Брадипн.", "Апноэ", "Апнейст.",
                   "Биота",   "Гаспинг", "Ч.-Стокса", "Диспноэ", "С рестр.", "Периодич."]

    fig = Figure(figsize=(7.6, 4.0), facecolor=_BG)

    # 1 — Scree
    ax1 = fig.add_subplot(2, 3, 1)
    pcs     = range(1, n_types + 1)
    cumvar  = np.cumsum(variances) * 100
    ax1.plot(pcs, variances * 100, "o-", color="#ff9800", lw=1.4, ms=3.5, label="Объясн. дисп.")
    ax1.plot(pcs, cumvar,          "s-", color="#00bcd4", lw=1.4, ms=3.5, label="Кумул. дисп.")
    ax1.axvline(x=3, color="#f44336", ls="--", alpha=0.8, lw=1, label="Оптимум")
    ax1.set_xlabel("Главные компоненты")
    ax1.set_ylabel("Доля дисперсии")
    ax1.legend(fontsize=5, facecolor=_BG, labelcolor=_TXT, framealpha=0.6)
    _ax_style(ax1, "Информативность компонент")

    # 2 — 2D scatter PC3-PC2
    ax2 = fig.add_subplot(2, 3, 2)
    for i in range(n_types):
        mask = labels == i
        ax2.scatter(pts[mask, 1], pts[mask, 2], c=_BT_COLORS[i], s=7, alpha=0.85,
                    label=names_short[i])
    ax2.legend(fontsize=4.5, facecolor=_BG, labelcolor=_TXT, framealpha=0.5,
               loc="upper right", ncol=1, handlelength=1, handletextpad=0.4)
    ax2.set_xlabel("PC3")
    ax2.set_ylabel("PC2")
    _ax_style(ax2, "Распределение в пространстве PC3-PC2")

    # 3 — Box plot
    ax3 = fig.add_subplot(2, 3, 3)
    intra, inter = [], []
    for i in range(n_types):
        mi = labels == i
        pi = pts[mi]
        for pp in pi:
            intra.append(float(np.linalg.norm(pi - pp, axis=1).mean()))
        for j in range(n_types):
            if i != j:
                mj = labels == j
                inter.append(float(np.linalg.norm(pts[mj] - pi.mean(0), axis=1).mean()))
    ax3.boxplot(
        [intra, inter], labels=["Внутрикл.", "Межкл."],
        patch_artist=True, widths=0.55,
        boxprops=dict(facecolor="#1a2535", color=_BRD),
        medianprops=dict(color="#00e5ff", lw=2),
        whiskerprops=dict(color=_DIM), capprops=dict(color=_DIM),
        flierprops=dict(marker="o", color=_DIM, ms=2.5),
    )
    _ax_style(ax3, "Сравнение расстояний")

    # 4 — Distance heatmap
    ax4 = fig.add_subplot(2, 3, 4)
    ax4.imshow(dist_mat, aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=dist_mat.max())
    ax4.set_xticks(range(n_types))
    ax4.set_yticks(range(n_types))
    ax4.set_xticklabels(names_short, rotation=90, fontsize=4.5)
    ax4.set_yticklabels(names_short, fontsize=4.5)
    threshold = dist_mat.max() * 0.55
    for i in range(n_types):
        for j in range(n_types):
            col = "white" if dist_mat[i, j] > threshold else "black"
            ax4.text(j, i, f"{dist_mat[i, j]:.1f}", ha="center", va="center",
                     fontsize=4, color=col)
    _ax_style(ax4, "Матрица расстояний между центрами классов")

    # 5 — Integral curves
    ax5 = fig.add_subplot(2, 3, 5)
    offset = 0.0
    for i, sig in enumerate(templates):
        y = sig + offset
        ax5.fill_between(t_arr, offset, y, color=_BT_COLORS[i], alpha=0.25)
        ax5.plot(t_arr, y, color=_BT_COLORS[i], lw=0.9, alpha=0.9)
        offset += 0.35
    ax5.set_xlabel("Время (с)")
    ax5.set_ylabel("Относит. проводимость")
    _ax_style(ax5, "Сравнение интегральных кривых для разных\nсценариев вентиляции")

    # 6 — 3D scatter
    ax6 = fig.add_subplot(2, 3, 6, projection="3d")
    ax6.set_facecolor(_AX)
    ax6.xaxis.pane.fill = ax6.yaxis.pane.fill = ax6.zaxis.pane.fill = False
    ax6.tick_params(colors=_DIM, labelsize=5)
    ax6.set_title("Распределение в пространстве\nPC1-PC2-PC3", fontsize=7, color=_TXT)
    for i in range(n_types):
        mask = labels == i
        ax6.scatter(pts[mask, 0], pts[mask, 1], pts[mask, 2],
                    c=_BT_COLORS[i], s=6, alpha=0.8)
    ax6.view_init(elev=20, azim=30)

    fig.tight_layout(pad=0.8)
    return fig


def _mock_breath_trace(t_arr: np.ndarray, freq: float, amp: float = 1.0) -> np.ndarray:
    """Одна кривая аэрации с реалистичной формой плетизмограммы."""
    return np.array([breath_waveform(t, freq, amp) for t in t_arr])


def _build_avg_figure() -> Figure:
    """Создаёт 12-панельную фигуру усреднённых кривых аэрации."""
    np.random.seed(7)
    t_arr = np.linspace(0, DISPLAY_WINDOW_SEC, int(DISPLAY_WINDOW_SEC * FS))
    base_freq = RR_BPM / 60.0

    fig = Figure(figsize=(7.6, 4.0), facecolor=_BG)
    for i, (key, color) in enumerate(zip(_BT_KEYS, _BT_COLORS)):
        ax = fig.add_subplot(3, 4, i + 1)
        amp = 0.9 - i * 0.04
        if i == 3:
            sig = np.zeros_like(t_arr)
        elif i == 7:
            env = np.abs(np.sin(np.pi * t_arr / (DISPLAY_WINDOW_SEC / 2)))
            sig = amp * env * _mock_breath_trace(t_arr, base_freq * 1.3)
        else:
            freq = base_freq * (0.85 + i * 0.05)
            sig = _mock_breath_trace(t_arr, freq, amp)
            sig += np.random.normal(0, 0.02, len(t_arr))
        ax.fill_between(t_arr, sig, 0, color=color, alpha=0.25)
        ax.plot(t_arr, sig, color=color, lw=1.2)
        ax.set_title(t(key)[:18], fontsize=6.5, color=_TXT, pad=2)
        _ax_style(ax)
        ax.set_xticks([])
        ax.set_yticks([])

    unused = fig.add_subplot(3, 4, 12)
    unused.set_visible(False)
    fig.tight_layout(pad=0.6)
    return fig


def _build_breathclf_pca_figure(data: BreathingModelVisualization) -> Figure:
    """Render PCA diagnostics stored in the integrated breathclf model."""
    scores = np.asarray(data.train_scores, dtype=float)
    labels = np.asarray(data.train_labels, dtype=int)
    n_classes = len(data.class_names)
    fig = Figure(figsize=(7.6, 4.0), facecolor=_BG)

    ax1 = fig.add_subplot(2, 2, 1)
    variance = np.asarray(data.explained_variance_ratio, dtype=float)
    components = np.arange(1, variance.size + 1)
    ax1.plot(components, variance * 100.0, "o-", color="#ff9800", lw=1.4, ms=3)
    ax1.plot(components, np.cumsum(variance) * 100.0, "s-", color="#00bcd4", lw=1.2, ms=3)
    ax1.set_xlabel("Главные компоненты")
    ax1.set_ylabel("Дисперсия, %")
    _ax_style(ax1, "Информативность компонент модели")

    ax2 = fig.add_subplot(2, 2, 2)
    if scores.ndim == 2 and scores.shape[1] >= 2:
        for index, name in enumerate(data.class_names):
            mask = labels == index
            ax2.scatter(
                scores[mask, 0], scores[mask, 1],
                color=_BT_COLORS[index % len(_BT_COLORS)], s=8, alpha=0.65,
                label=name,
            )
        if data.current_score is not None and len(data.current_score) >= 2:
            ax2.scatter(
                data.current_score[0], data.current_score[1],
                marker="*", s=120, color="white", edgecolor="#f44336",
                linewidth=1.2, label="Текущая кривая", zorder=10,
            )
    ax2.legend(
        fontsize=4.3, facecolor=_BG, labelcolor=_TXT, framealpha=0.55,
        loc="best", ncol=2,
    )
    ax2.set_xlabel("PC1")
    ax2.set_ylabel("PC2")
    _ax_style(ax2, "Обучающая выборка и текущая кривая")

    ax3 = fig.add_subplot(2, 2, 3)
    centroids = []
    if scores.ndim == 2 and scores.shape[1] >= 2:
        for index in range(n_classes):
            group = scores[labels == index, :2]
            centroids.append(group.mean(axis=0) if len(group) else np.zeros(2))
    matrix = np.asarray(centroids, dtype=float)
    distances = (
        np.linalg.norm(matrix[:, None, :] - matrix[None, :, :], axis=2)
        if len(matrix) else np.zeros((n_classes, n_classes))
    )
    ax3.imshow(distances, aspect="auto", cmap="magma")
    ax3.set_xticks(range(n_classes))
    ax3.set_yticks(range(n_classes))
    short = [name[:12] for name in data.class_names]
    ax3.set_xticklabels(short, rotation=90, fontsize=4.5)
    ax3.set_yticklabels(short, fontsize=4.5)
    _ax_style(ax3, "Расстояния между центрами классов")

    ax4 = fig.add_subplot(2, 2, 4, projection="3d")
    ax4.set_facecolor(_AX)
    ax4.xaxis.pane.fill = ax4.yaxis.pane.fill = ax4.zaxis.pane.fill = False
    ax4.tick_params(colors=_DIM, labelsize=5)
    ax4.set_title("Пространство PC1–PC3", fontsize=7, color=_TXT)
    if scores.ndim == 2 and scores.shape[1] >= 3:
        for index in range(n_classes):
            mask = labels == index
            ax4.scatter(
                scores[mask, 0], scores[mask, 1], scores[mask, 2],
                color=_BT_COLORS[index % len(_BT_COLORS)], s=6, alpha=0.65,
            )
        if data.current_score is not None and len(data.current_score) >= 3:
            ax4.scatter(
                data.current_score[0], data.current_score[1], data.current_score[2],
                marker="*", s=110, color="white", edgecolor="#f44336",
            )
    ax4.view_init(elev=20, azim=30)
    fig.tight_layout(pad=0.8)
    return fig


def _build_breathclf_templates_figure(data: BreathingModelVisualization) -> Figure:
    """Render the actual class templates embedded in the model bundle."""
    templates = np.asarray(data.templates, dtype=float)
    fig = Figure(figsize=(7.6, 4.0), facecolor=_BG)
    count = min(len(data.class_names), templates.shape[0] if templates.ndim == 2 else 0)
    for index in range(count):
        ax = fig.add_subplot(3, 4, index + 1)
        values = templates[index]
        time_values = np.arange(values.size, dtype=float) / data.sample_rate_hz
        color = _BT_COLORS[index % len(_BT_COLORS)]
        ax.fill_between(time_values, values, 0.0, color=color, alpha=0.25)
        ax.plot(time_values, values, color=color, lw=1.1)
        ax.set_title(data.class_names[index][:22], fontsize=6.3, color=_TXT, pad=2)
        _ax_style(ax)
        ax.set_xticks([])
        ax.set_yticks([])
    for index in range(count, 12):
        unused = fig.add_subplot(3, 4, index + 1)
        unused.set_visible(False)
    fig.tight_layout(pad=0.6)
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# Вкладка 2: Аэрация ГЛОБАЛЬНАЯ
# ═══════════════════════════════════════════════════════════════════════════════

class _GlobalLeftPanel(QWidget):
    """Левая панель вкладки «Глобальная аэрация»: визуализация + параметры + кнопки."""

    analysis_selection_changed = Signal(float, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(380)
        self.setStyleSheet(
            f"background:{C['bg_panel']};border-right:2px solid {C['border']};"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 8)
        lay.setSpacing(6)

        selection = QWidget()
        selection.setStyleSheet("background:transparent;")
        sl = QGridLayout(selection)
        sl.setContentsMargins(2, 0, 2, 0)
        sl.setHorizontalSpacing(6)
        sl.setVerticalSpacing(3)
        self._window_label = QLabel()
        self._cycle_label = QLabel()
        self._window_combo = QComboBox()
        self._cycle_combo = QComboBox()
        for seconds in (5.0, 15.0, 30.0, 60.0):
            self._window_combo.addItem("", seconds)
        for count in (None, 1, 3, 5):
            self._cycle_combo.addItem("", count)
        self._window_combo.setCurrentIndex(2)
        for widget in (
            self._window_label, self._cycle_label,
            self._window_combo, self._cycle_combo,
        ):
            widget.setStyleSheet(
                f"color:{C['text']};background:{C['bg_card']};"
                f"font-size:{FONT_SMALL}px;"
            )
        sl.addWidget(self._window_label, 0, 0)
        sl.addWidget(self._window_combo, 0, 1)
        sl.addWidget(self._cycle_label, 1, 0)
        sl.addWidget(self._cycle_combo, 1, 1)
        lay.addWidget(selection)
        self._window_combo.currentIndexChanged.connect(self._emit_selection)
        self._cycle_combo.currentIndexChanged.connect(self._emit_selection)

        self.lung_viz = LungVizWidget()
        self.lung_viz.setMinimumHeight(220)
        lay.addWidget(self.lung_viz)

        lay.addWidget(_hsep())

        grid = QWidget()
        gl = QGridLayout(grid)
        gl.setContentsMargins(2, 2, 2, 2)
        gl.setSpacing(8)
        self.bx_t   = _PBox("T, %")
        self.bx_r   = _PBox("R, %")
        self.bx_l   = _PBox("L, %")
        self.bx_lr  = _PBox("R/L")
        self.bx_vd  = _PBox("V/D")
        self.bx_rr  = _PBox("ЧД")
        gl.addWidget(self.bx_t,  0, 0)
        gl.addWidget(self.bx_r,  1, 0)
        gl.addWidget(self.bx_l,  2, 0)
        gl.addWidget(self.bx_lr, 0, 1)
        gl.addWidget(self.bx_vd, 1, 1)
        gl.addWidget(self.bx_rr, 2, 1)
        lay.addWidget(grid)

        self._analysis_status = QLabel()
        self._analysis_status.setWordWrap(True)
        self._analysis_status.setStyleSheet(
            f"color:{C['text_dim']};font-size:{FONT_SMALL}px;background:transparent;"
        )
        lay.addWidget(self._analysis_status)

        lay.addWidget(_hsep())
        lay.addStretch()

        self.btn_start = QPushButton(_start_btn_text(False))
        _configure_start_btn(self.btn_start)
        lay.addWidget(self.btn_start)

        counters = QWidget()
        counters.setStyleSheet("background:transparent;")
        cl = QGridLayout(counters)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setHorizontalSpacing(12)
        cl.setVerticalSpacing(6)
        self.cnt_eit = DurationCounter("param_eit_duration", stacked=True)
        self.cnt_es  = DurationCounter("param_es_time", stacked=True)
        cl.addWidget(self.cnt_eit, 0, 0)
        cl.addWidget(self.cnt_es,  0, 1)
        lay.addWidget(counters)

        i18n.language_changed.connect(self.retranslate)
        self.retranslate()

    def sync_start(self, running: bool):
        self.btn_start.setText(_start_btn_text(running))
        self.btn_start.setStyleSheet(_START_STYLE_RUN if running else "")

    def set_counters(self, eit: str, es: str):
        self.cnt_eit.set_value(eit)
        self.cnt_es.set_value(es)

    def update_params(self, snap):
        self.bx_t.set_value(snap.t_pct)
        self.bx_r.set_value(snap.r_pct)
        self.bx_l.set_value(snap.l_pct)
        self.bx_lr.set_value(snap.lr_ratio)
        self.bx_vd.set_value(snap.vd_ratio)
        self.bx_rr.set_value(round(snap.rr, 0) if snap.rr is not None else None)
        self.lung_viz.update_state(
            snap.phase,
            snap.roi_pct,
            getattr(snap, "reconstruction_map", None),
            getattr(snap, "absolute_conductivity_map", None),
        )
        snap_quality = getattr(snap, "quality", "unavailable")
        quality = quality_text(snap_quality)
        cycles = getattr(snap, "complete_cycle_count", 0)
        selected = getattr(snap, "selected_cycle_count", None)
        cycle_text = f"{cycles}" if selected is None else f"{cycles}/{selected}"
        self._analysis_status.setText(
            f"{t('analysis_quality')}: {quality} · "
            f"{t('analysis_cycles_found')}: {cycle_text}\n"
            f"{getattr(snap, 'algorithm_version', '—')} · "
            f"{getattr(snap, 'analyzed_sample_count', 0)} "
            f"{t('analysis_samples')}"
        )
        params = getattr(snap, "algorithm_parameters", None)
        if params is not None:
            detector_key = (
                "sys_peak_detector_legacy"
                if params.peak_detection_method == "legacy"
                else "sys_peak_detector_derivative"
            )
            self._analysis_status.setToolTip(
                f"{t('analysis_param_sample_rate')}: "
                f"{params.sample_rate_hz:g} {t('analysis_unit_hz')}; "
                f"{t('analysis_param_smoothing')}: {params.smoothing_samples}; "
                f"{t('analysis_param_min_cycles')}: {params.minimum_complete_cycles}; "
                f"{t('analysis_param_rr_range')}: "
                f"{params.minimum_rr_bpm:g}–{params.maximum_rr_bpm:g} {t('wave_rr_unit')}; "
                f"{t('sys_engineering_peak_detector')} {t(detector_key)}; "
                f"{t('ui_reason_label')}: "
                f"{quality_reason_text(getattr(snap, 'quality_reason', None))}"
            )

    @property
    def analysis_selection(self) -> tuple[float, int | None]:
        return (
            float(self._window_combo.currentData()),
            self._cycle_combo.currentData(),
        )

    def _emit_selection(self):
        window, cycles = self.analysis_selection
        self.analysis_selection_changed.emit(window, cycles)

    def retranslate(self):
        self._window_label.setText(t("analysis_interval"))
        self._cycle_label.setText(t("analysis_cycles"))
        for index, seconds in enumerate((5, 15, 30, 60)):
            self._window_combo.setItemText(index, f"{seconds} {t('analysis_seconds_short')}")
        self._cycle_combo.setItemText(0, t("analysis_all_cycles"))
        for index, count in enumerate((1, 3, 5), start=1):
            self._cycle_combo.setItemText(index, str(count))
        self.cnt_eit.retranslate()
        self.cnt_es.retranslate()


class GlobalTab(QWidget):
    """Вкладка «Аэрация ГЛОБАЛЬНАЯ»: левая панель + панель осциллограмм."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._left  = _GlobalLeftPanel()
        self._waves = WaveformPanel(show_regional=False, expand_global=True)

        lay.addWidget(self._left)
        lay.addWidget(self._waves, stretch=1)

        self.btn_start = self._left.btn_start
        self.btn_event = self._waves.btn_event

    @property
    def analysis_selection(self) -> tuple[float, int | None]:
        return self._left.analysis_selection

    def sync_start(self, running: bool):
        self._left.sync_start(running)

    def set_counters(self, eit: str, es: str):
        self._left.set_counters(eit, es)

    def update_data(self, snap, waves: dict):
        self._left.update_params(snap)
        self._waves.update_all(
            waves, snap.rr, snap.roi_pct,
            trends={
                "global": snap.trend_global,
                "r": snap.trend_r,
                "l": snap.trend_l,
                "rois": snap.roi_trends,
            },
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Вкладка 3: Аэрация РЕГИОНАРНАЯ
# ═══════════════════════════════════════════════════════════════════════════════

class RegionalTab(QWidget):
    """Вкладка «Аэрация РЕГИОНАРНАЯ»."""

    def __init__(self, parent=None, *, roi_count: int = 8):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Верхняя часть: визуализация + параметры ───────────────────────────
        upper = QWidget()
        upper.setMaximumHeight(168)
        upper.setStyleSheet(f"background:{C['bg_panel']};")
        upper_lay = QHBoxLayout(upper)
        upper_lay.setContentsMargins(8, 6, 8, 6)
        upper_lay.setSpacing(10)

        self.lung_viz = LungVizWidget()
        self.lung_viz.setFixedSize(150, 150)
        upper_lay.addWidget(self.lung_viz)

        pg = QWidget()
        pg.setStyleSheet("background:transparent;")
        pgl = QGridLayout(pg)
        pgl.setContentsMargins(0, 0, 0, 0)
        pgl.setHorizontalSpacing(8)
        pgl.setVerticalSpacing(6)
        self.bx_t  = _PBox("T, %", w=128)
        self.bx_r  = _PBox("R, %", w=128)
        self.bx_l  = _PBox("L, %", w=128)
        self.bx_lr = _PBox("R/L",  w=128)
        self.bx_vd = _PBox("V/D",  w=128)
        pgl.addWidget(self.bx_t,  0, 0)
        pgl.addWidget(self.bx_r,  0, 1)
        pgl.addWidget(self.bx_l,  0, 2)
        pgl.addWidget(self.bx_lr, 1, 0)
        pgl.addWidget(self.bx_vd, 1, 1)
        upper_lay.addWidget(pg)
        upper_lay.addStretch()
        root.addWidget(upper)
        root.addWidget(_hsep())

        self._waves = RegionalWaveformPanel(roi_count=roi_count)
        root.addWidget(self._waves, stretch=1)

        # ── Нижняя панель ─────────────────────────────────────────────────────
        self._bar = _BottomBar()
        root.addWidget(self._bar)

        self.btn_start = self._bar.btn_start
        self.btn_event = self._bar.btn_event

    def set_roi_count(self, roi_count: int) -> None:
        self._waves.set_roi_count(roi_count)

    def sync_start(self, running: bool):
        self._bar.sync_start(running)

    def set_counters(self, eit: str, es: str):
        self._bar.set_counters(eit, es)

    def update_data(self, snap, waves: dict):
        self.bx_t.set_value(snap.t_pct)
        self.bx_r.set_value(snap.r_pct)
        self.bx_l.set_value(snap.l_pct)
        self.bx_lr.set_value(snap.lr_ratio)
        self.bx_vd.set_value(snap.vd_ratio)
        self.lung_viz.update_state(
            snap.phase,
            snap.roi_pct,
            getattr(snap, "reconstruction_map", None),
            getattr(snap, "absolute_conductivity_map", None),
        )
        self._waves.update_all(
            waves, snap.roi_pct, snap.r_pct, snap.l_pct,
            trends={
                "global": snap.trend_global,
                "r": snap.trend_r,
                "l": snap.trend_l,
                "rois": snap.roi_trends,
            },
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Вкладка 1: Тип патологического дыхания
# ═══════════════════════════════════════════════════════════════════════════════

class _BreathingTypeBtn(QLabel):
    """Кликабельная метка типа дыхания с переносом длинного текста."""

    clicked = Signal()

    def __init__(self, text: str, color: str, parent=None):
        super().__init__(text, parent)
        self._color = color
        self._active = False
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._apply_style(False)

    def _apply_style(self, active: bool):
        self._active = active
        bg = self._color if active else C["bg_card"]
        fg = "#000000" if active else self._color
        self.setStyleSheet(
            f"background:{bg};color:{fg};"
            f"border:1px solid {self._color};border-radius:3px;"
            f"font-size:{FONT_SMALL}px;padding:6px;"
        )

    def set_active(self, active: bool):
        self._apply_style(active)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _BreathingTypePanel(QWidget):
    """Правая колонка: список возможных типов дыхания."""

    manual_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self.setStyleSheet(f"background:{C['bg_panel']};border-left:1px solid {C['border']};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        self._title = QLabel(t("analysis_possible_types"))
        self._title.setWordWrap(True)
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet(
            f"color:{C['text']};font-size:{FONT_LABEL}px;font-weight:bold;"
            f"background:{C['bg_card']};border:1px solid {C['border']};"
            f"border-radius:3px;padding:4px;"
        )
        lay.addWidget(self._title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background:transparent;")

        list_w = QWidget()
        list_lay = QVBoxLayout(list_w)
        list_lay.setContentsMargins(0, 0, 0, 0)
        list_lay.setSpacing(4)

        self._btns: list[_BreathingTypeBtn] = []
        self._selected: int | None = None
        for i, (key, color) in enumerate(zip(_BT_KEYS, _BT_COLORS)):
            btn = _BreathingTypeBtn(t(key), color)
            btn.clicked.connect(lambda idx=i: self._select(idx))
            list_lay.addWidget(btn)
            self._btns.append(btn)

        list_lay.addStretch()
        scroll.setWidget(list_w)
        lay.addWidget(scroll, stretch=1)
        i18n.language_changed.connect(self.retranslate)

    def _select(self, idx: int):
        if self._selected == idx:
            self._selected = None
        else:
            self._selected = idx
        for i, btn in enumerate(self._btns):
            btn.set_active(i == self._selected)
        if self._selected is not None:
            self.manual_selected.emit(self._selected)

    def retranslate(self):
        self._title.setText(t("analysis_possible_types"))
        for btn, key in zip(self._btns, _BT_KEYS):
            btn.setText(t(key))


class PathologyTab(QWidget):
    """Вкладка «Тип патологического дыхания»."""

    def __init__(self, classification_service=None, parent=None):
        super().__init__(parent)
        self._classification_service = classification_service
        self._last_result = None
        self._model_visualization_signature: str | None = None
        self._model_visualization_has_current = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Внутренние подвкладки (PCA / Усреднённые) ─────────────────────────
        sub_bar = QWidget()
        sub_bar.setFixedHeight(48)
        sub_bar.setStyleSheet(f"background:{C['bg_header']};border-bottom:1px solid {C['border']};")
        sb_lay = QHBoxLayout(sub_bar)
        sb_lay.setContentsMargins(4, 4, 4, 4)
        sb_lay.setSpacing(4)

        self._sub_stack = QStackedWidget()

        self._btn_pca = QPushButton(t("analysis_sub_pca"))
        self._btn_avg = QPushButton(t("analysis_sub_avg"))
        for btn in (self._btn_pca, self._btn_avg):
            btn.setFixedHeight(38)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background:{C['bg_card']};color:{C['text']};
                    border:1px solid {C['border']};border-radius:3px;
                    font-size:{TAB_BAR_SUB_FONT}px;padding:4px 12px;
                }}
                QPushButton:hover {{background:{C['blue_dark']};}}
                QPushButton[active="true"] {{
                    background:{C['blue']};font-weight:bold;
                }}
            """)
            sb_lay.addWidget(btn)
        sb_lay.addStretch()

        self._btn_pca.clicked.connect(lambda: self._switch_sub(0))
        self._btn_avg.clicked.connect(lambda: self._switch_sub(1))

        root.addWidget(sub_bar)

        # ── Контент подвкладок + правая колонка ───────────────────────────────
        middle = QWidget()
        middle_lay = QHBoxLayout(middle)
        middle_lay.setContentsMargins(0, 0, 0, 0)
        middle_lay.setSpacing(0)

        self._pca_canvas = FigureCanvas(_build_pca_figure())
        self._avg_canvas = FigureCanvas(_build_avg_figure())
        for canvas in (self._pca_canvas, self._avg_canvas):
            canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._sub_stack.addWidget(self._pca_canvas)
        self._sub_stack.addWidget(self._avg_canvas)

        middle_lay.addWidget(self._sub_stack, stretch=1)

        self._bt_panel = _BreathingTypePanel()
        self._bt_panel.manual_selected.connect(self._set_manual_assessment)
        middle_lay.addWidget(self._bt_panel)
        root.addWidget(middle, stretch=1)

        # ── Строка «Текущий тип дыхания» ──────────────────────────────────────
        self._type_lbl = QLabel(
            f"{t('analysis_current_type')}: {t('analysis_bt_undetermined')}"
        )
        self._type_lbl.setAlignment(Qt.AlignCenter)
        self._type_lbl.setFixedHeight(26)
        self._type_lbl.setStyleSheet(
            f"color:{C['text']};font-size:{FONT_BASE}px;"
            f"background:{C['bg_panel']};border-top:1px solid {C['border']};"
        )
        root.addWidget(self._type_lbl)
        self._manual_lbl = QLabel(f"{t('analysis_manual_type')}: —")
        self._manual_lbl.setAlignment(Qt.AlignCenter)
        self._manual_lbl.setFixedHeight(24)
        self._manual_lbl.setStyleSheet(
            f"color:{C['text_dim']};font-size:{FONT_SMALL}px;background:{C['bg_panel']};"
        )
        root.addWidget(self._manual_lbl)

        # ── Нижняя панель ─────────────────────────────────────────────────────
        self._bar = _BottomBar()
        root.addWidget(self._bar)

        self.btn_start = self._bar.btn_start
        self.btn_event = self._bar.btn_event
        self._switch_sub(0)
        i18n.language_changed.connect(self.retranslate)

    def _switch_sub(self, idx: int):
        self._sub_stack.setCurrentIndex(idx)
        self._btn_pca.setProperty("active", idx == 0)
        self._btn_avg.setProperty("active", idx == 1)
        self._btn_pca.style().unpolish(self._btn_pca)
        self._btn_pca.style().polish(self._btn_pca)
        self._btn_avg.style().unpolish(self._btn_avg)
        self._btn_avg.style().polish(self._btn_avg)

    def sync_start(self, running: bool):
        self._bar.sync_start(running)

    def set_counters(self, eit: str, es: str):
        self._bar.set_counters(eit, es)

    def update_data(self, snap, waves: dict):
        service = self._classification_service
        if service is None:
            detected = t("analysis_bt_undetermined")
            detail = ""
        else:
            now = utc_now()
            values = np.asarray(waves.get("global", []), dtype=float)
            duration = len(values) / FS
            result = service.classify(values, FS, now - timedelta(seconds=duration), now)
            self._last_result = result
            keys = {
                BreathingClass.EUPNEA: "analysis_bt_eupnea",
                BreathingClass.TACHYPNEA: "analysis_bt_tachypnea",
                BreathingClass.BRADYPNEA: "analysis_bt_bradypnea",
                BreathingClass.APNEA: "analysis_bt_apnea",
                BreathingClass.PERIODIC: "analysis_bt_periodic",
                BreathingClass.RESTRICTIVE: "analysis_bt_restrictive",
                BreathingClass.RETRACTIVE: "analysis_bt_retraction",
                BreathingClass.GASPING: "analysis_bt_gasping",
                BreathingClass.DYSPNEA: "analysis_bt_dyspnea",
                BreathingClass.CENTRAL_APNEA: "analysis_bt_apnea_central",
                BreathingClass.OBSTRUCTIVE_APNEA: "analysis_bt_apnea_obstructive",
                BreathingClass.MIXED_APNEA: "analysis_bt_apnea_mixed",
                BreathingClass.REFLEX_APNEA: "analysis_bt_apnea_reflex",
                BreathingClass.UNDETERMINED: "analysis_bt_undetermined",
            }
            detected = t(keys[result.breathing_class])
            detail = f" · {result.confidence * 100:.0f}% · {result.algorithm_version}"
            if result.reason == "experimental_model_not_clinically_validated":
                detail += f" · {t('analysis_classifier_experimental')}"
            self._type_lbl.setToolTip(
                t(f"analysis_reason_{result.reason}") if result.reason else ""
            )
            if (
                self._model_visualization_signature is None
                or not self._model_visualization_has_current
            ):
                visualization = service.visualization(values, FS)
                if visualization is not None:
                    self._apply_model_visualization(visualization)
        self._type_lbl.setText(f"{t('analysis_current_type')}: {detected}{detail}")

    def _apply_model_visualization(
        self, visualization: BreathingModelVisualization
    ) -> None:
        has_current = visualization.current_score is not None
        if (
            visualization.signature == self._model_visualization_signature
            and (self._model_visualization_has_current or not has_current)
        ):
            return
        selected = self._sub_stack.currentIndex()
        old_pca, old_avg = self._pca_canvas, self._avg_canvas
        self._sub_stack.removeWidget(old_pca)
        self._sub_stack.removeWidget(old_avg)
        old_pca.deleteLater()
        old_avg.deleteLater()
        self._pca_canvas = FigureCanvas(_build_breathclf_pca_figure(visualization))
        self._avg_canvas = FigureCanvas(_build_breathclf_templates_figure(visualization))
        for canvas in (self._pca_canvas, self._avg_canvas):
            canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._sub_stack.addWidget(self._pca_canvas)
        self._sub_stack.addWidget(self._avg_canvas)
        self._sub_stack.setCurrentIndex(selected)
        self._model_visualization_signature = visualization.signature
        self._model_visualization_has_current = has_current

    def _set_manual_assessment(self, index: int):
        if self._classification_service is None:
            return
        classes = (
            BreathingClass.EUPNEA, BreathingClass.PERIODIC,
            BreathingClass.TACHYPNEA, BreathingClass.RETRACTIVE,
            BreathingClass.GASPING, BreathingClass.BRADYPNEA,
            BreathingClass.DYSPNEA, BreathingClass.CENTRAL_APNEA,
            BreathingClass.OBSTRUCTIVE_APNEA, BreathingClass.MIXED_APNEA,
            BreathingClass.REFLEX_APNEA,
        )
        assessment = self._classification_service.set_manual_assessment(
            classes[index], "local-operator"
        )
        self._manual_lbl.setText(
            f"{t('analysis_manual_type')}: {t(_BT_KEYS[index])} · {assessment.author}"
        )

    def retranslate(self):
        self._btn_pca.setText(t("analysis_sub_pca"))
        self._btn_avg.setText(t("analysis_sub_avg"))
        detected = (
            t("analysis_bt_undetermined") if self._last_result is None
            else t({
                BreathingClass.EUPNEA: "analysis_bt_eupnea",
                BreathingClass.TACHYPNEA: "analysis_bt_tachypnea",
                BreathingClass.BRADYPNEA: "analysis_bt_bradypnea",
                BreathingClass.APNEA: "analysis_bt_apnea",
                BreathingClass.PERIODIC: "analysis_bt_periodic",
                BreathingClass.RESTRICTIVE: "analysis_bt_restrictive",
                BreathingClass.RETRACTIVE: "analysis_bt_retraction",
                BreathingClass.GASPING: "analysis_bt_gasping",
                BreathingClass.DYSPNEA: "analysis_bt_dyspnea",
                BreathingClass.CENTRAL_APNEA: "analysis_bt_apnea_central",
                BreathingClass.OBSTRUCTIVE_APNEA: "analysis_bt_apnea_obstructive",
                BreathingClass.MIXED_APNEA: "analysis_bt_apnea_mixed",
                BreathingClass.REFLEX_APNEA: "analysis_bt_apnea_reflex",
                BreathingClass.UNDETERMINED: "analysis_bt_undetermined",
            }[self._last_result.breathing_class])
        )
        self._type_lbl.setText(f"{t('analysis_current_type')}: {detected}")
        assessment = (
            self._classification_service.manual_assessment
            if self._classification_service is not None else None
        )
        if assessment is None:
            self._manual_lbl.setText(f"{t('analysis_manual_type')}: —")
        self._bt_panel.retranslate()


# ═══════════════════════════════════════════════════════════════════════════════
# Главный экран АНАЛИЗ
# ═══════════════════════════════════════════════════════════════════════════════

_TAB_ACTIVE_STYLE = f"""
    QPushButton {{
        background:{C['warn']}; color:#000;
        border:none; border-bottom:2px solid #e65c00;
        font-size:{TAB_BAR_FONT}px; font-weight:bold; padding:6px 10px;
    }}
"""
_TAB_IDLE_STYLE = f"""
    QPushButton {{
        background:#3d2e00; color:{C['warn']};
        border:none; border-bottom:1px solid {C['border']};
        font-size:{TAB_BAR_FONT}px; padding:6px 10px;
    }}
    QPushButton:hover {{ background:#4d3b00; }}
"""


class AnalysisScreen(QWidget):
    """Экран АНАЛИЗ с тремя вкладками и внедрённым источником данных."""

    def __init__(
        self,
        monitoring: MonitoringData,
        parent=None,
        *,
        marker_service: EventMarkerService | None = None,
        classification_service: BreathingClassificationService | None = None,
        engineering_settings=None,
    ):
        super().__init__(parent)

        self._monitoring = monitoring
        self._marker_service = marker_service
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Панель вкладок ────────────────────────────────────────────────────
        tab_bar = QWidget()
        tab_bar.setFixedHeight(72)
        tab_bar.setStyleSheet(
            f"background:{C['bg_header']};border-bottom:1px solid {C['border']};"
        )
        tbl = QHBoxLayout(tab_bar)
        tbl.setContentsMargins(0, 0, 0, 0)
        tbl.setSpacing(0)

        self._btn_path = QPushButton(t("analysis_tab_pathology"))
        self._btn_glob = QPushButton(t("analysis_tab_global"))
        self._btn_reg  = QPushButton(t("analysis_tab_regional"))

        for btn in (self._btn_path, self._btn_reg, self._btn_glob):
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            tbl.addWidget(btn)

        self._btn_path.clicked.connect(lambda: self._switch_tab(0))
        self._btn_reg.clicked.connect(lambda: self._switch_tab(1))
        self._btn_glob.clicked.connect(lambda: self._switch_tab(2))

        root.addWidget(tab_bar)

        # ── Стек вкладок ──────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        root.addWidget(self._stack, stretch=1)

        self._path_tab   = PathologyTab(classification_service)
        self._global_tab = GlobalTab()
        self._reg_tab = RegionalTab(
            roi_count=(engineering_settings.current.roi_count if engineering_settings else 8)
        )
        if engineering_settings is not None:
            self._unsubscribe_engineering = engineering_settings.subscribe(
                lambda settings: self._reg_tab.set_roi_count(settings.roi_count)
            )

        self._stack.addWidget(self._path_tab)
        self._stack.addWidget(self._reg_tab)
        self._stack.addWidget(self._global_tab)
        self._global_tab._left.analysis_selection_changed.connect(
            self._configure_global_analysis
        )

        self._switch_tab(2)  # «Глобальная» по умолчанию

        # ── Таймеры ───────────────────────────────────────────────────────────
        self._paint_timer = QTimer(self)
        self._paint_timer.timeout.connect(self._on_paint)
        self._paint_timer.start(PAINT_MS)

        timers = SessionTimers.instance(self)
        timers.updated.connect(self._on_timers_updated)
        self._on_timers_updated(*timers.values())

        i18n.language_changed.connect(self.retranslate)

    # ── Вспомогательные ───────────────────────────────────────────────────────

    def _all_tabs(self):
        return [self._path_tab, self._global_tab, self._reg_tab]

    def _switch_tab(self, idx: int):
        self._stack.setCurrentIndex(idx)
        styles = [_TAB_IDLE_STYLE] * 3
        styles[idx] = _TAB_ACTIVE_STYLE
        for btn, style in zip(
            (self._btn_path, self._btn_reg, self._btn_glob), styles
        ):
            btn.setStyleSheet(style)

    def sync_start(self, running: bool):
        for tab in self._all_tabs():
            tab.sync_start(running)

    def _on_paint(self):
        current = self._stack.currentWidget()
        window = (
            current.analysis_selection[0]
            if current is self._global_tab else DISPLAY_WINDOW_SEC
        )
        if hasattr(self._monitoring, "read_view"):
            view = self._monitoring.read_view(window)
            snap, waves = view.snapshot, view.waveforms
        else:
            snap = self._monitoring.snapshot
            waves = self._monitoring.get_waveforms(window)
        if hasattr(current, "update_data"):
            current.update_data(snap, waves)
        events = (
            self._marker_service.list_for_current_study()
            if self._marker_service is not None else ()
        )
        if current is self._global_tab:
            current._waves.set_event_markers(events, waves["time"])
        elif current is self._reg_tab:
            current._waves.set_event_markers(events, waves["time"])

    def _configure_global_analysis(
        self, window_seconds: float, cycle_count: int | None
    ) -> None:
        configure = getattr(self._monitoring, "configure_aeration_analysis", None)
        if configure is not None:
            configure(window_seconds=window_seconds, cycle_count=cycle_count)

    @property
    def event_buttons(self):
        return tuple(
            tab.btn_event for tab in self._all_tabs()
            if getattr(tab, "btn_event", None) is not None
        )

    def _on_timers_updated(self, eit_str: str, es_str: str):
        for tab in self._all_tabs():
            tab.set_counters(eit_str, es_str)

    def retranslate(self):
        self._btn_path.setText(t("analysis_tab_pathology"))
        self._btn_glob.setText(t("analysis_tab_global"))
        self._btn_reg.setText(t("analysis_tab_regional"))
        if hasattr(self._path_tab, "retranslate"):
            self._path_tab.retranslate()
