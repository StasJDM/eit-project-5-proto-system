"""Shared dialog used by every event-marker entry point."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
    QTextEdit, QVBoxLayout,
)

from ..application import MARKER_TYPES
from ..domain import Event
from ..i18n import t
from ..styles import C, FONT_BASE


_TYPE_KEYS = {
    "cough": "marker_type_cough",
    "procedure": "marker_type_procedure",
    "position_change": "marker_type_position",
    "suction": "marker_type_suction",
    "operator_note": "marker_type_note",
}


@dataclass(frozen=True, slots=True)
class MarkerDialogValues:
    event_type: str
    description: str
    author: str


class EventMarkerDialog(QDialog):
    def __init__(
        self,
        position_seconds: float,
        default_author: str,
        *,
        correction: Event | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("marker_correction_title" if correction else "marker_dialog_title"))
        self.setMinimumWidth(520)
        self.setStyleSheet(f"""
            QDialog {{ background:{C['bg_panel']}; color:{C['text']}; }}
            QLabel {{ color:{C['text']}; font-size:{FONT_BASE}px; }}
            QLineEdit, QTextEdit, QComboBox {{
                background:{C['bg_card']}; color:{C['text']};
                border:1px solid {C['border_light']}; border-radius:4px;
                padding:6px; font-size:{FONT_BASE}px;
            }}
        """)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._position = QLabel(_format_position(position_seconds))
        self._position.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow(t("marker_position"), self._position)

        self._type = QComboBox()
        for value in MARKER_TYPES:
            self._type.addItem(t(_TYPE_KEYS[value]), value)
        if correction is not None:
            index = self._type.findData(correction.event_type)
            if index >= 0:
                self._type.setCurrentIndex(index)
        form.addRow(t("marker_type"), self._type)

        self._author = QLineEdit(default_author)
        form.addRow(t("marker_author"), self._author)
        layout.addLayout(form)
        layout.addWidget(QLabel(t("marker_description")))
        self._description = QTextEdit()
        self._description.setPlaceholderText(t("marker_description_hint"))
        if correction is not None:
            self._description.setPlainText(correction.text)
        layout.addWidget(self._description)

        self._error = QLabel()
        self._error.setStyleSheet(f"color:{C['alarm']};")
        layout.addWidget(self._error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(t("svc_dlg_save"))
        buttons.button(QDialogButtonBox.Cancel).setText(t("svc_dlg_cancel"))
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> MarkerDialogValues:
        return MarkerDialogValues(
            event_type=str(self._type.currentData()),
            description=self._description.toPlainText().strip(),
            author=self._author.text().strip(),
        )

    def _validate(self) -> None:
        values = self.values()
        if not values.description or not values.author:
            self._error.setText(t("marker_required"))
            return
        self.accept()


def _format_position(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    minutes, milliseconds = divmod(total_ms, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
