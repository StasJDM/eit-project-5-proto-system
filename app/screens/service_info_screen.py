"""Окно СЛУЖЕБНАЯ ИНФОРМАЦИЯ — протоколирование неблагоприятных событий.

Алгоритм (блок-схема рис. 7.8):
  Загрузка журнала → отображение протокола → действие пользователя:
    - Добавить событие: ввод через текстовые поля → сохранение записи → обновление списка
    - Фильтр: выбор фильтра (по типу) → обновление списка
    - Навигация: переход в выбранное окно (обрабатывается NavPanel)
"""

from datetime import datetime, timezone

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QComboBox, QDialog, QTextEdit, QLineEdit, QDateTimeEdit,
    QSizePolicy, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, Signal

from ..application import (
    AdverseEventError, AdverseEventService, EventMarkerError, EventMarkerService,
)
from ..domain import Event, EventCategory
from ..styles import C, FONT_BASE, FONT_SMALL, FONT_TITLE, FONT_LABEL, FONT_BTN
from ..i18n import t, i18n
from .event_marker_dialog import EventMarkerDialog, _format_position

# ── Event type keys (i18n) ────────────────────────────────────────────────────

_EVENT_TYPES = [
    "marker_type_cough",
    "marker_type_procedure",
    "marker_type_position",
    "marker_type_suction",
    "marker_type_note",
    "svc_type_tech_error",
    "svc_type_adverse_event",
    "svc_type_adverse_phenom",
    "svc_type_operator_note",
]
_ADVERSE_TYPE_KEYS = [
    "svc_type_tech_error", "svc_type_adverse_event",
    "svc_type_adverse_phenom", "svc_type_operator_note",
]

# ── Add-event dialog ──────────────────────────────────────────────────────────

class AddEventDialog(QDialog):
    """Модальный диалог ввода сведений о событии через текстовые поля."""

    def __init__(
        self, parent=None, *, default_author: str = "local-operator", original=None,
        event_types=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(t("svc_dlg_title"))
        self.setFixedSize(520, 380)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {C['bg_panel']};
                color: {C['text']};
            }}
            QLabel {{
                background: transparent;
                color: {C['text']};
                font-size: {FONT_BASE}px;
            }}
            QLineEdit, QTextEdit {{
                background-color: {C['bg_card']};
                color: {C['text']};
                border: 1px solid {C['border_light']};
                border-radius: 4px;
                padding: 6px 8px;
                font-size: {FONT_BASE}px;
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border-color: {C['blue_light']};
            }}
            QComboBox {{
                background-color: {C['bg_card']};
                color: {C['text']};
                border: 1px solid {C['border_light']};
                border-radius: 4px;
                padding: 6px 8px;
                font-size: {FONT_BASE}px;
                min-height: 30px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {C['bg_panel']};
                color: {C['text']};
                border: 1px solid {C['border']};
                selection-background-color: {C['blue']};
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        # Title
        lbl_title = QLabel(t("svc_dlg_title"))
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet(f"font-size:18px;font-weight:bold;color:{C['text']};background:transparent;")
        lay.addWidget(lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{C['border']};")
        lay.addWidget(sep)

        # Date/time row
        row_dt = QHBoxLayout()
        lbl_dt = QLabel(t("svc_dlg_datetime"))
        lbl_dt.setFixedWidth(140)
        self._edit_dt = QLineEdit(datetime.now().strftime("%d.%m.%Y  %H:%M:%S"))
        row_dt.addWidget(lbl_dt)
        row_dt.addWidget(self._edit_dt)
        lay.addLayout(row_dt)

        # Type row
        row_type = QHBoxLayout()
        lbl_type = QLabel(t("svc_dlg_type"))
        lbl_type.setFixedWidth(140)
        self._combo_type = QComboBox()
        for key in event_types or _EVENT_TYPES:
            self._combo_type.addItem(t(key), key)
        row_type.addWidget(lbl_type)
        row_type.addWidget(self._combo_type)
        lay.addLayout(row_type)

        # Description
        lbl_desc = QLabel(t("svc_dlg_desc"))
        lay.addWidget(lbl_desc)
        self._edit_desc = QTextEdit()
        self._edit_desc.setPlaceholderText(t("svc_dlg_desc_hint"))
        self._edit_desc.setFixedHeight(90)
        lay.addWidget(self._edit_desc)

        row_author = QHBoxLayout()
        lbl_author = QLabel(t("marker_author"))
        lbl_author.setFixedWidth(140)
        self._edit_author = QLineEdit(default_author)
        row_author.addWidget(lbl_author)
        row_author.addWidget(self._edit_author)
        lay.addLayout(row_author)

        if original is not None:
            self._edit_dt.setText(original.occurred_at_utc.astimezone().strftime("%d.%m.%Y  %H:%M:%S"))
            self._edit_dt.setReadOnly(True)
            self._edit_desc.setPlainText(original.text)
            original_keys = {
                "technical_error": "svc_type_tech_error",
                "adverse_event": "svc_type_adverse_event",
                "adverse_phenomenon": "svc_type_adverse_phenom",
                "operator_note": "svc_type_operator_note",
            }
            index = self._combo_type.findData(original_keys.get(original.event_type))
            if index >= 0:
                self._combo_type.setCurrentIndex(index)

        lay.addStretch()

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"color:{C['border']};")
        lay.addWidget(sep2)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._btn_cancel = QPushButton(t("svc_dlg_cancel"))
        self._btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['bg_nav']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 4px;
                padding: 8px 20px;
                font-size: {FONT_BASE}px;
            }}
            QPushButton:hover {{ background-color: {C['nav_hover']}; }}
        """)
        self._btn_cancel.clicked.connect(self.reject)

        self._btn_save = QPushButton(t("svc_dlg_save"))
        self._btn_save.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['ok']};
                color: white;
                border: 1px solid #1b5e20;
                border-radius: 4px;
                padding: 8px 20px;
                font-size: {FONT_BASE}px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {C['ok_hover']}; }}
            QPushButton:pressed {{ background-color: #1b5e20; }}
        """)
        self._btn_save.clicked.connect(self._save)

        btn_row.addWidget(self._btn_cancel)
        btn_row.addWidget(self._btn_save)
        lay.addLayout(btn_row)

    def _save(self):
        desc = self._edit_desc.toPlainText().strip()
        if not desc or not self._edit_author.text().strip():
            self._edit_desc.setStyleSheet(
                self._edit_desc.styleSheet() +
                f"border-color:{C['alarm']};"
            )
            return
        self.accept()

    def result_event(self) -> dict:
        return {
            "dt":   self._edit_dt.text().strip(),
            "type": self._combo_type.currentData(),
            "desc": self._edit_desc.toPlainText().strip(),
            "author": self._edit_author.text().strip(),
        }


# ── Event row widget ──────────────────────────────────────────────────────────

_ROW_H   = 58
_NUM_W   = 48
_DT_W    = 210
_TYPE_W  = 270
_SVC_LABEL_FONT = round(FONT_BASE * 1.2)   # +20 % для подзаголовка и фильтра


class _EventRow(QFrame):
    """One row in the event log."""

    correction_requested = Signal(object)

    def __init__(self, num: int, event: dict, even: bool, parent=None):
        super().__init__(parent)
        bg = C['bg_card'] if even else C['bg_panel']
        self.setFixedHeight(_ROW_H)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border-left: 1px solid {C['border']};
                border-right: 1px solid {C['border']};
                border-bottom: 1px solid {C['border']};
            }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._cell(str(num), width=_NUM_W, center=True, dim=True))
        lay.addWidget(self._vsep())
        lay.addWidget(self._cell(event["dt"], width=_DT_W, mono=True))
        lay.addWidget(self._vsep())

        type_lbl = self._type_badge(event["type"])
        type_lbl.setFixedWidth(_TYPE_W)
        type_lbl.setWordWrap(True)
        lay.addWidget(type_lbl)
        lay.addWidget(self._vsep())

        desc_lbl = self._cell(event["desc"])
        desc_lbl.setToolTip(event["desc"])
        desc_lbl.setWordWrap(True)
        desc_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        desc_lbl.setContentsMargins(10, 4, 10, 4)
        lay.addWidget(desc_lbl, stretch=1)
        source_event = event.get("event")
        if source_event is not None:
            correction = QPushButton(t("marker_correction"))
            correction.setFixedWidth(110)
            correction.clicked.connect(
                lambda _checked=False, item=source_event: self.correction_requested.emit(item)
            )
            lay.addWidget(correction)

    # ── Badge colours by event type ──────────────────────────────────────────

    _TYPE_COLORS = {
        "svc_type_tech_error":     (C['alarm'],  "#1a0505"),
        "svc_type_adverse_event":  (C['warn'],   "#1a1205"),
        "svc_type_adverse_phenom": (C['warn'],   "#1a1205"),
        "svc_type_operator_note":  (C['blue_light'], C['blue_dark']),
        "marker_type_cough":       (C['warn'], C['bg_main']),
        "marker_type_procedure":   (C['blue_light'], C['blue_dark']),
        "marker_type_position":    (C['ok_hover'], C['bg_main']),
        "marker_type_suction":     (C['warn'], C['bg_main']),
        "marker_type_note":        (C['text'], C['bg_main']),
    }

    def _type_badge(self, type_key: str) -> QLabel:
        fg, bg = self._TYPE_COLORS.get(type_key, (C['text'], C['bg_main']))
        lbl = QLabel(t(type_key))
        lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        lbl.setContentsMargins(10, 6, 10, 6)
        lbl.setStyleSheet(
            f"color:{fg};background:transparent;font-size:{FONT_BASE}px;font-weight:bold;"
        )
        return lbl

    def _cell(self, text: str, width: int = -1,
              center: bool = False, dim: bool = False, mono: bool = False) -> QLabel:
        lbl = QLabel(text)
        if width > 0:
            lbl.setFixedWidth(width)
        lbl.setAlignment(Qt.AlignCenter if center else Qt.AlignVCenter | Qt.AlignLeft)
        lbl.setContentsMargins(10, 6, 10, 6)
        color = C['text_dim'] if dim else C['text']
        mono_style = "font-family:monospace;" if mono else ""
        lbl.setStyleSheet(
            f"color:{color};background:transparent;font-size:{FONT_BASE}px;{mono_style}"
        )
        return lbl

    def _vsep(self) -> QWidget:
        line = QWidget()
        line.setFixedWidth(1)
        line.setStyleSheet(f"background-color:{C['border']};")
        return line


# ── Service info screen ───────────────────────────────────────────────────────

class ServiceInfoScreen(QWidget):
    """Протоколирование неблагоприятных событий текущего сеанса."""

    def __init__(
        self,
        marker_service: EventMarkerService | None = None,
        adverse_event_service: AdverseEventService | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._marker_service = marker_service
        self._adverse_event_service = adverse_event_service
        self.setStyleSheet(f"background-color:{C['bg_main']};")

        self._events: list[dict] = self._load_events()
        self._filter_type: str | None = None   # None = all
        self._search_text = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 24, 40, 24)
        outer.setSpacing(14)

        # ── Title ─────────────────────────────────────────────────────────────
        self._lbl_title = QLabel(t("screen_service"))
        self._lbl_title.setAlignment(Qt.AlignCenter)
        self._lbl_title.setStyleSheet(
            f"color:{C['text']};font-size:26px;font-weight:bold;background:transparent;"
        )
        outer.addWidget(self._lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{C['border']};")
        outer.addWidget(sep)

        # ── Session label ────────────────────────────────────────────────────
        self._lbl_session = QLabel(t("svc_session_label"))
        self._lbl_session.setStyleSheet(
            f"color:{C['text_dim']};font-size:{_SVC_LABEL_FONT}px;background:transparent;"
        )
        outer.addWidget(self._lbl_session)

        # ── Toolbar (filter + add button) ─────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self._lbl_filter = QLabel(t("svc_filter_type"))
        self._lbl_filter.setStyleSheet(
            f"color:{C['text_dim']};font-size:{_SVC_LABEL_FONT}px;background:transparent;"
        )
        toolbar.addWidget(self._lbl_filter)

        self._combo_filter = QComboBox()
        self._combo_filter.setFixedWidth(220)
        self._combo_filter.setStyleSheet(f"""
            QComboBox {{
                background-color: {C['bg_card']};
                color: {C['text']};
                border: 1px solid {C['border_light']};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: {FONT_BASE}px;
                min-height: 28px;
            }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background-color: {C['bg_panel']};
                color: {C['text']};
                border: 1px solid {C['border']};
                selection-background-color: {C['blue']};
            }}
        """)
        self._rebuild_combo()
        self._combo_filter.currentIndexChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._combo_filter)

        self._edit_search = QLineEdit()
        self._edit_search.setPlaceholderText(t("svc_search_placeholder"))
        self._edit_search.setFixedWidth(180)
        self._edit_search.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self._edit_search)

        self._date_from = QDateTimeEdit()
        self._date_from.setDisplayFormat("dd.MM.yyyy HH:mm")
        self._date_from.setCalendarPopup(True)
        self._date_from.setDateTime(datetime(2000, 1, 1))
        self._date_from.dateTimeChanged.connect(lambda _value: self._rebuild_list())
        toolbar.addWidget(self._date_from)
        self._date_to = QDateTimeEdit()
        self._date_to.setDisplayFormat("dd.MM.yyyy HH:mm")
        self._date_to.setCalendarPopup(True)
        self._date_to.setDateTime(datetime.now().replace(hour=23, minute=59, second=59))
        self._date_to.dateTimeChanged.connect(lambda _value: self._rebuild_list())
        toolbar.addWidget(self._date_to)

        self._btn_reset = QPushButton(t("svc_btn_reset_filter"))
        self._btn_reset.setFixedHeight(32)
        self._btn_reset.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['bg_nav']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 4px;
                padding: 0 14px;
                font-size: {FONT_BASE}px;
            }}
            QPushButton:hover {{ background-color: {C['nav_hover']}; }}
        """)
        self._btn_reset.clicked.connect(self._reset_filter)
        toolbar.addWidget(self._btn_reset)

        toolbar.addStretch()

        self._btn_add = QPushButton(t("svc_btn_add"))
        self._btn_add.setFixedHeight(32)
        self._btn_add.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['ok']};
                color: white;
                border: 1px solid #1b5e20;
                border-radius: 4px;
                padding: 0 18px;
                font-size: {FONT_BASE}px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {C['ok_hover']}; }}
            QPushButton:pressed {{ background-color: #1b5e20; }}
        """)
        self._btn_add.clicked.connect(self._open_add_dialog)
        toolbar.addWidget(self._btn_add)

        outer.addLayout(toolbar)

        # ── Table header ──────────────────────────────────────────────────────
        self._hdr = self._build_header()
        outer.addWidget(self._hdr)

        # ── Scrollable event list ─────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{
                background: {C['bg_main']};
                width: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {C['border']};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self._list_container = QWidget()
        self._list_container.setStyleSheet("background:transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)

        scroll.setWidget(self._list_container)
        outer.addWidget(scroll, stretch=1)

        # ── Empty-state label ─────────────────────────────────────────────────
        self._lbl_empty = QLabel(t("svc_no_events"))
        self._lbl_empty.setAlignment(Qt.AlignCenter)
        self._lbl_empty.setStyleSheet(
            f"color:{C['text_lo']};font-size:15px;background:transparent;"
        )
        self._lbl_empty.hide()
        outer.addWidget(self._lbl_empty)

        self._rebuild_list()

        i18n.language_changed.connect(self.retranslate)

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setFixedHeight(44)
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {C['bg_nav']};
                border: 1px solid {C['border']};
                border-bottom: 2px solid {C['blue']};
            }}
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._hcells: dict[str, QLabel] = {}

        for key, width, center in [
            ("svc_col_num",      _NUM_W,  True),
            ("svc_col_datetime", _DT_W,   False),
            ("svc_col_type",     _TYPE_W, False),
            ("svc_col_desc",     -1,      False),
        ]:
            lbl = QLabel(t(key))
            if width > 0:
                lbl.setFixedWidth(width)
            else:
                lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            lbl.setAlignment(Qt.AlignCenter if center else Qt.AlignVCenter | Qt.AlignLeft)
            lbl.setContentsMargins(10, 6, 10, 6)
            if key == "svc_col_datetime":
                lbl.setStyleSheet(
                    f"color:{C['text']};font-size:{FONT_BASE}px;font-weight:bold;"
                    f"background:transparent;font-family:monospace;"
                )
            else:
                lbl.setStyleSheet(
                    f"color:{C['text']};font-size:{FONT_BASE}px;font-weight:bold;background:transparent;"
                )
            self._hcells[key] = lbl
            lay.addWidget(lbl)
            if key != "svc_col_desc":
                sep = QWidget()
                sep.setFixedWidth(1)
                sep.setStyleSheet(f"background-color:{C['border']};")
                lay.addWidget(sep)

        return frame

    # ── List rebuild ──────────────────────────────────────────────────────────

    def _rebuild_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        visible = [
            ev for ev in self._events
            if (self._filter_type is None or ev["type"] == self._filter_type)
            and self._date_from.dateTime().toPython() <= ev["occurred_local"]
            <= self._date_to.dateTime().toPython()
            and self._search_text in f'{ev["desc"]} {ev["type"]}'.casefold()
        ]

        if not visible:
            self._lbl_empty.show()
        else:
            self._lbl_empty.hide()

        for i, ev in enumerate(reversed(visible)):
            row = _EventRow(len(visible) - i, ev, even=(i % 2 == 0))
            row.correction_requested.connect(self._open_correction_dialog)
            self._list_layout.addWidget(row)

        self._list_layout.addStretch()

    def _rebuild_combo(self):
        self._combo_filter.blockSignals(True)
        self._combo_filter.clear()
        self._combo_filter.addItem(t("svc_filter_all"), None)
        for key in _EVENT_TYPES:
            self._combo_filter.addItem(t(key), key)
        # restore selection
        if self._filter_type is not None:
            idx = self._combo_filter.findData(self._filter_type)
            if idx >= 0:
                self._combo_filter.setCurrentIndex(idx)
        self._combo_filter.blockSignals(False)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_filter_changed(self, index: int):
        self._filter_type = self._combo_filter.itemData(index)
        self._rebuild_list()

    def _reset_filter(self):
        self._combo_filter.setCurrentIndex(0)
        self._edit_search.clear()

    def _on_search_changed(self, text: str):
        self._search_text = text.strip().casefold()
        self._rebuild_list()

    def _open_add_dialog(self):
        if self._adverse_event_service is not None:
            self._open_adverse_dialog()
            return
        QMessageBox.warning(self, t("study_action_error_title"), t("marker_unavailable"))

    def _open_adverse_dialog(self):
        service = self._adverse_event_service
        if service is None:
            return
        dlg = AddEventDialog(
            self, default_author=service.default_author, event_types=_ADVERSE_TYPE_KEYS
        )
        if dlg.exec() != QDialog.Accepted:
            return
        values = dlg.result_event()
        type_map = {
            "svc_type_tech_error": "technical_error",
            "svc_type_adverse_event": "adverse_event",
            "svc_type_adverse_phenom": "adverse_phenomenon",
            "svc_type_operator_note": "operator_note",
        }
        try:
            occurred_local = datetime.strptime(values["dt"], "%d.%m.%Y  %H:%M:%S").replace(
                tzinfo=datetime.now().astimezone().tzinfo
            )
            service.create(
                type_map.get(values["type"], "operator_note"), values["desc"],
                values["author"], occurred_at_utc=occurred_local.astimezone(timezone.utc),
            )
        except (ValueError, AdverseEventError):
            QMessageBox.warning(self, t("study_action_error_title"), t("marker_unavailable"))
            return
        self.refresh()

    def _open_marker_dialog(self):
        service = self._marker_service
        if service is None:
            return
        if not service.has_current_study:
            QMessageBox.warning(self, t("study_action_error_title"), t("marker_unavailable"))
            return
        dialog = EventMarkerDialog(
            service.current_position_seconds,
            service.default_author,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            service.create(values.event_type, values.description, values.author)
        except EventMarkerError:
            QMessageBox.warning(self, t("study_action_error_title"), t("marker_unavailable"))
            return
        self.refresh()

    def _open_correction_dialog(self, original: Event):
        if original.category is EventCategory.ADVERSE_EVENT:
            self._open_adverse_correction(original)
            return
        service = self._marker_service
        if service is None:
            return
        dialog = EventMarkerDialog(
            original.position_seconds,
            service.default_author or original.author,
            correction=original,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        try:
            service.correct(
                original.id,
                values.description,
                values.author,
                event_type=values.event_type,
            )
        except EventMarkerError:
            QMessageBox.warning(self, t("study_action_error_title"), t("marker_unavailable"))
            return
        self.refresh()

    def _open_adverse_correction(self, original: Event):
        service = self._adverse_event_service
        if service is None:
            return
        dialog = AddEventDialog(
            self, default_author=service.default_author or original.author,
            original=original, event_types=_ADVERSE_TYPE_KEYS,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.result_event()
        type_map = {
            "svc_type_tech_error": "technical_error",
            "svc_type_adverse_event": "adverse_event",
            "svc_type_adverse_phenom": "adverse_phenomenon",
            "svc_type_operator_note": "operator_note",
        }
        try:
            service.correct(
                original.id, values["desc"], values["author"],
                event_type=type_map.get(values["type"], original.event_type),
            )
        except AdverseEventError:
            QMessageBox.warning(self, t("study_action_error_title"), t("marker_unavailable"))
            return
        self.refresh()

    def refresh(self):
        self._events = self._load_events()
        self._rebuild_list()

    def _load_events(self) -> list[dict]:
        if self._adverse_event_service is None and self._marker_service is None:
            return []
        type_keys = {
            "cough": "marker_type_cough",
            "procedure": "marker_type_procedure",
            "position_change": "marker_type_position",
            "suction": "marker_type_suction",
            "operator_note": "marker_type_note",
        }
        result = []
        if self._adverse_event_service is not None:
            events = self._adverse_event_service.list_current()
        else:
            events = self._marker_service.list_for_current_study()
        adverse_type_keys = {
            "technical_error": "svc_type_tech_error",
            "adverse_event": "svc_type_adverse_event",
            "adverse_phenomenon": "svc_type_adverse_phenom",
            "operator_note": "svc_type_operator_note",
        }
        for event in events:
            correction = (
                f"{t('marker_corrects')} {str(event.corrects_event_id)[:8]} · "
                if event.corrects_event_id else ""
            )
            result.append({
                "dt": event.occurred_at_utc.astimezone().strftime("%d.%m.%Y  %H:%M:%S"),
                "type": (adverse_type_keys if event.category is EventCategory.ADVERSE_EVENT else type_keys).get(event.event_type, "marker_type_note"),
                "desc": (
                    f"{correction}{event.text} "
                    f"[{event.author} · {_format_position(event.position_seconds)}]"
                ),
                "event": event,
                "occurred_local": event.occurred_at_utc.astimezone().replace(tzinfo=None),
            })
        return result

    # ── i18n ─────────────────────────────────────────────────────────────────

    def retranslate(self):
        self._lbl_title.setText(t("screen_service"))
        self._lbl_session.setText(t("svc_session_label"))
        self._lbl_filter.setText(t("svc_filter_type"))
        self._btn_reset.setText(t("svc_btn_reset_filter"))
        self._btn_add.setText(t("svc_btn_add"))
        self._lbl_empty.setText(t("svc_no_events"))
        self._edit_search.setPlaceholderText(t("svc_search_placeholder"))

        for key, lbl in self._hcells.items():
            lbl.setText(t(key))

        self._rebuild_combo()
        self._rebuild_list()
