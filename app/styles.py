"""Dark medical theme: colours, constants, global stylesheet."""

# ── Colour palette ──────────────────────────────────────────────────────────
C = {
    # backgrounds
    "bg_main":    "#0d1117",
    "bg_panel":   "#111827",
    "bg_header":  "#080d14",
    "bg_wave":    "#080e14",
    "bg_nav":     "#0f1923",
    "bg_card":    "#161b22",
    "bg_table":   "#252a31",
    "bg_table_alt": "#2b3139",
    "bg_table_header": "#323943",

    # borders
    "border":       "#1e3a5f",
    "border_light": "#2d4a70",

    # blues (primary UI colour)
    "blue":         "#1565c0",
    "blue_dark":    "#0d3a7a",
    "blue_hover":   "#0d47a1",
    "blue_light":   "#1976d2",

    # text
    "text":     "#e8eaed",
    "text_dim": "#8b949e",
    "text_lo":  "#4d5a6a",

    # state / alert
    "alarm":    "#d32f2f",
    "warn":     "#f9a825",
    "ok":       "#2e7d32",
    "ok_hover": "#388e3c",

    # waveform line colours — 1 global + 8 ROIs (см. AERATION_* ниже)
    "w0": "#ff9800",
    "w1": "#e53935",
    "w2": "#f44336",
    "w3": "#ff5252",
    "w4": "#ff867c",
    "w5": "#2e7d32",
    "w6": "#43a047",
    "w7": "#66bb6a",
    "w8": "#81c784",

    # lung viz
    "lung_right": "#f44336",
    "lung_left":  "#43a047",
    "thorax":     "#0a1628",

    # nav active / hover
    "nav_active":               "#1565c0",
    "nav_active_surround":      "#0b4f91",
    "nav_active_surround_edge": "#2196f3",
    "nav_hover":                "#0d2744",
}

DEFAULT_APPLICATION_BACKGROUND_COLOR = C["bg_main"]

# ── Закреплённые цвета типов аэрации (T / R / L) ────────────────────────────
AERATION_COLOR_T = "#ff9800"  # глобальная — оранжевый
AERATION_COLOR_R = "#f44336"  # правое лёгкое — красный
AERATION_COLOR_L = "#4caf50"  # левое лёгкое — зелёный

# Оттенки ROI (4 зоны на каждую сторону)
AERATION_ROI_R = [C["w1"], C["w2"], C["w3"], C["w4"]]
AERATION_ROI_L = [C["w5"], C["w6"], C["w7"], C["w8"]]

# index 0 = global; 1–4 = ROI правого; 5–8 = ROI левого
WAVE_COLORS = [AERATION_COLOR_T, *AERATION_ROI_R, *AERATION_ROI_L]

SECTION_COLORS = {"T": AERATION_COLOR_T, "R": AERATION_COLOR_R, "L": AERATION_COLOR_L}

# ── Typography (12″ clinical display) ───────────────────────────────────────
FONT_BASE        = 18   # body, inputs (было 13)
FONT_SMALL       = 16   # вторичные подписи (было 9–12)
FONT_LABEL       = 18   # метки полей
FONT_VALUE       = 24   # числовые показатели
FONT_MEDICAL_VALUE = 32 # ключевые медицинские показатели для чтения с расстояния
FONT_TITLE       = 20   # заголовки секций (было 12)
FONT_BTN         = 18   # кнопки (было 13)
FONT_BTN_ACTION  = 20   # жёлтые action-кнопки (было 12)
FONT_BTN_START   = 22   # Старт (было 15)
FONT_HEADER      = 18   # строка состояния (было 12–13)
FONT_TAB         = 22   # вкладки верхнего уровня
FONT_TAB_SUB     = 20   # подвкладки
FONT_NAV         = 20   # навигация (было 13)

# Алиасы для обратной совместимости
TAB_BAR_FONT = FONT_TAB
TAB_BAR_SUB_FONT = FONT_TAB_SUB

# Bottom-bar action buttons (may contain two-line labels)
ACTION_BTN_HEIGHT = 60


def start_button_style() -> str:
    """Shared unmistakably green style for the available Start action."""
    return f"""
        QPushButton {{
            background-color: {C['ok']};
            color: white;
            border: 1px solid #1b5e20;
            border-radius: 4px;
            font-size: {FONT_BTN_START}px;
            font-weight: bold;
            padding: 10px 20px;
            min-height: 38px;
        }}
        QPushButton:hover {{ background-color: {C['ok_hover']}; }}
        QPushButton:pressed {{ background-color: #1b5e20; }}
        QPushButton:disabled {{
            background-color: #254d32;
            color: #9fb7a7;
            border-color: #326541;
        }}
    """


def stop_button_style() -> str:
    """Shared Stop style with the same typography as the Start action."""
    return f"""
        QPushButton {{
            background-color: {C['alarm']};
            color: white;
            border: 1px solid #b71c1c;
            border-radius: 4px;
            font-size: {FONT_BTN_START}px;
            font-weight: bold;
            padding: 10px 20px;
            min-height: 38px;
        }}
        QPushButton:hover {{ background-color: #c62828; }}
        QPushButton:pressed {{ background-color: #b71c1c; }}
    """


def yellow_btn_style() -> str:
    return f"""
        QPushButton {{
            background-color: #3a2e00;
            color: {C['warn']};
            border: 1px solid #7a6000;
            border-radius: 4px;
            font-size: {FONT_BTN_ACTION}px;
            font-weight: 500;
            padding: 8px 16px;
        }}
        QPushButton:hover {{ background-color: #4a3c00; }}
        QPushButton:pressed {{ background-color: #2a2000; }}
    """


def configure_action_btn(btn, min_width: int = 160) -> None:
    """Size a bottom-bar yellow action button for one- or two-line labels."""
    btn.setFixedHeight(ACTION_BTN_HEIGHT)
    btn.setMinimumWidth(min_width)
    btn.setStyleSheet(yellow_btn_style())


EVENT_MARKER_BTN_HEIGHT = 52
EVENT_MARKER_BTN_MIN_WIDTH = 240


def event_marker_btn_style() -> str:
    return f"""
        QPushButton {{
            background-color: #1a1200;
            color: {C['warn']};
            border: 1px solid #7a6000;
            border-radius: 4px;
            font-size: {FONT_BTN_ACTION}px;
            font-weight: bold;
            padding: 8px 20px;
        }}
        QPushButton:hover {{ background-color: #2a1e00; }}
        QPushButton:pressed {{ background-color: #120c00; }}
    """


def configure_event_marker_btn(btn, min_width: int = EVENT_MARKER_BTN_MIN_WIDTH) -> None:
    """Size the event-marker button (used on monitoring waveform screens)."""
    btn.setFixedHeight(EVENT_MARKER_BTN_HEIGHT)
    btn.setMinimumWidth(min_width)
    btn.setStyleSheet(event_marker_btn_style())


def waveform_bg_dark():
    return C["bg_wave"]


# ── Global stylesheet ────────────────────────────────────────────────────────
def stylesheet(background_color: str | None = None) -> str:
    bg_main = background_color or DEFAULT_APPLICATION_BACKGROUND_COLOR
    return f"""
/* ── Base ── */
QWidget {{
    background-color: {bg_main};
    color: {C['text']};
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: {FONT_BASE}px;
}}

/* ── Buttons ── */
QPushButton {{
    background-color: {C['blue']};
    color: {C['text']};
    border: 1px solid {C['border_light']};
    border-radius: 4px;
    padding: 6px 14px;
    font-size: {FONT_BTN}px;
    font-weight: 500;
}}
QPushButton:hover  {{ background-color: {C['blue_hover']}; }}
QPushButton:pressed {{ background-color: {C['blue_dark']}; }}
QPushButton:disabled {{ background-color: #1a2535; color: {C['text_lo']}; }}

/* ── Start button override ── */
QPushButton#btn_start {{
    background-color: {C['ok']};
    font-size: {FONT_BTN_START}px;
    font-weight: bold;
    padding: 10px 20px;
    min-height: 38px;
    border: 1px solid #1b5e20;
}}
QPushButton#btn_start:hover  {{ background-color: {C['ok_hover']}; }}
QPushButton#btn_start:pressed {{ background-color: #1b5e20; }}

/* ── Nav buttons ── */
QPushButton#nav_btn {{
    background-color: {C['bg_nav']};
    border: 1px solid {C['border']};
    border-radius: 0;
    text-align: left;
    padding: 12px 12px;
    font-size: {FONT_NAV}px;
}}
QPushButton#nav_btn:hover   {{ background-color: {C['nav_hover']}; }}
QPushButton#nav_btn[active="true"] {{
    background-color: {C['nav_active']};
    border-color: {C['blue_light']};
    font-weight: bold;
}}

/* ── Scrollbars ── */
QScrollBar:vertical {{
    background: {bg_main};
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C['border']};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

/* ── Frames / separators ── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {C['border']};
}}

/* ── ToolTips ── */
QToolTip {{
    background-color: #1a2535;
    color: {C['text']};
    border: 1px solid {C['border']};
    padding: 4px 8px;
}}
"""
