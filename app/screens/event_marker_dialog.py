"""Touch-friendly event type chooser used by every marker entry point."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QGridLayout, QPushButton, QVBoxLayout

from ..domain import Event
from ..i18n import t
from ..styles import C, FONT_BTN


_TYPE_BUTTONS = (
    ("cough", "marker_type_cough"),
    ("procedure", "marker_type_procedure"),
    ("position_change", "marker_type_position"),
    ("operator_note", "marker_type_other"),
)


@dataclass(frozen=True, slots=True)
class MarkerDialogValues:
    event_type: str
    description: str
    author: str


class EventMarkerDialog(QDialog):
    """Offers four large choices and closes immediately after selection."""

    def __init__(
        self,
        position_seconds: float,
        default_author: str,
        *,
        correction: Event | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        del position_seconds  # The marker position is captured before this dialog opens.
        self._author = default_author.strip()
        self._event_type = "operator_note"
        self.setWindowTitle(t("marker_dialog_title"))
        self.setMinimumSize(640, 300)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{ background:{C['bg_panel']}; color:{C['text']}; }}
            QPushButton {{
                background:{C['bg_card']}; color:{C['text']};
                border:2px solid {C['border_light']}; border-radius:10px;
                padding:14px; font-size:{FONT_BTN}px; font-weight:bold;
            }}
            QPushButton:pressed {{
                background:{C['blue_dark']}; border-color:{C['blue_light']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        layout.addLayout(grid)

        selected_type = correction.event_type if correction is not None else None
        for index, (event_type, text_key) in enumerate(_TYPE_BUTTONS):
            button = QPushButton(t(text_key))
            button.setMinimumHeight(105)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("event_type", event_type)
            if event_type == selected_type:
                button.setStyleSheet(
                    f"border-color:{C['blue_light']}; background:{C['blue_dark']};"
                )
            button.clicked.connect(
                lambda _checked=False, value=event_type: self._select(value)
            )
            grid.addWidget(button, index // 2, index % 2)

    def values(self) -> MarkerDialogValues:
        return MarkerDialogValues(
            event_type=self._event_type,
            description="",
            author=self._author,
        )

    def _select(self, event_type: str) -> None:
        self._event_type = event_type
        self.accept()


def _format_position(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    minutes, milliseconds = divmod(total_ms, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
