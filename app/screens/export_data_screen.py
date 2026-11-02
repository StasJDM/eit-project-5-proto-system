"""Study/category selection and generation of versioned export packages."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..application.exporting import EXPORT_CATEGORIES, ExportError, StudyExportService
from ..i18n import i18n, t
from ..styles import C, FONT_BASE, FONT_TITLE, configure_action_btn, yellow_btn_style
from ..technical_logging import get_logger, technical_event
from ..ui_text import study_conclusion_text, study_status_text


_logger = get_logger("export")
_CATEGORY_LABELS = {
    "metadata": "exp_category_metadata",
    "metrics": "exp_category_metrics",
    "trends": "exp_category_trends",
    "events": "exp_category_events",
    "raw_data": "exp_category_raw",
}


def _fmt_btn_style() -> str:
    return yellow_btn_style() + f"""
        QPushButton[active="true"] {{
            background-color:#5a4500;border-color:{C['warn']};font-weight:bold;
        }}
    """


class _SectionBox(QWidget):
    def __init__(self, title_key: str, parent=None):
        super().__init__(parent)
        self._title_key = title_key
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QWidget()
        header.setFixedHeight(36)
        header.setStyleSheet(f"background:{C['blue_dark']};border:1px solid {C['border']};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 0, 10, 0)
        self._title = QLabel(t(title_key))
        self._title.setStyleSheet(f"color:white;font-size:{FONT_TITLE}px;font-weight:bold;")
        header_layout.addWidget(self._title)
        root.addWidget(header)
        self._body = QWidget()
        self._body.setStyleSheet(f"background:{C['bg_panel']};border:1px solid {C['border']};")
        self.body_layout = QVBoxLayout(self._body)
        self.body_layout.setContentsMargins(10, 10, 10, 10)
        self.body_layout.setSpacing(7)
        root.addWidget(self._body)

    def retranslate(self):
        self._title.setText(t(self._title_key))


class _StudyRow(QWidget):
    def __init__(self, study, patient, on_change, parent=None):
        super().__init__(parent)
        self._study = study
        self.study_id: UUID = study.id
        self.checkbox = QCheckBox()
        self.checkbox.stateChanged.connect(on_change)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(self.checkbox)
        self._patient_name = " ".join(filter(None, (
            getattr(patient, "family_name", None),
            getattr(patient, "given_name", None),
            getattr(patient, "middle_name", None),
        ))) or getattr(patient, "external_id", None) or "—"
        self._label = QLabel()
        self._label.setStyleSheet(f"color:{C['text']};font-size:{FONT_BASE}px;")
        layout.addWidget(self._label, 1)
        date = QLabel(study.created_at_utc.astimezone().strftime("%d.%m.%Y %H:%M"))
        layout.addWidget(date)
        self._details = QPushButton(t("exp_btn_details"))
        self._details.clicked.connect(self._show_details)
        layout.addWidget(self._details)
        self.setStyleSheet(f"background:{C['bg_card']};border:1px solid {C['border']};")
        self.retranslate()

    def _show_details(self):
        study = self._study
        QMessageBox.information(
            self,
            t("exp_btn_details"),
            f"ID: {study.id}\n"
            f"{t('exp_detail_patient')}: {self._patient_name}\n"
            f"{t('exp_detail_status')}: {study_status_text(study.status)}\n"
            f"{t('exp_detail_created')}: "
            f"{study.created_at_utc.astimezone().strftime('%d.%m.%Y %H:%M')}\n"
            f"{t('exp_detail_conclusion')}: {study_conclusion_text(study.conclusion)}",
        )

    def retranslate(self):
        self._label.setText(
            f"{self._patient_name} · {str(self._study.id)[:8]} · "
            f"{study_status_text(self._study.status)}"
        )
        self._details.setText(t("exp_btn_details"))


class ExportDataScreen(QWidget):
    _FORMATS = ("JSON", "EXCEL", "CSV")

    def __init__(self, service: StudyExportService | None = None, default_directory: Path | None = None, parent=None):
        super().__init__(parent)
        self._service = service
        self._default_directory = Path(default_directory or "exports")
        self._active_fmt = "JSON"
        self._history_rows: list[_StudyRow] = []
        self.setStyleSheet(f"background:{C['bg_main']};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        columns = QHBoxLayout(content)

        left = QVBoxLayout()
        columns.addLayout(left, 30)
        self._box_format = _SectionBox("exp_format_title")
        self._fmt_btns = {}
        for fmt in self._FORMATS:
            button = QPushButton(fmt)
            button.setFixedHeight(42)
            button.setStyleSheet(_fmt_btn_style())
            button.clicked.connect(lambda _=False, value=fmt: self._select_format(value))
            self._box_format.body_layout.addWidget(button)
            self._fmt_btns[fmt] = button
        left.addWidget(self._box_format)
        self._box_categories = _SectionBox("exp_data_title")
        self._category_checks: dict[str, QCheckBox] = {}
        for category in EXPORT_CATEGORIES:
            checkbox = QCheckBox(t(_CATEGORY_LABELS[category]))
            checkbox.setChecked(category != "raw_data")
            checkbox.stateChanged.connect(self._update_estimate)
            self._box_categories.body_layout.addWidget(checkbox)
            self._category_checks[category] = checkbox
        left.addWidget(self._box_categories)
        left.addStretch()

        right = QVBoxLayout()
        columns.addLayout(right, 70)
        self._box_history = _SectionBox("exp_history_title")
        self._history_layout = self._box_history.body_layout
        right.addWidget(self._box_history)
        self._privacy = QLabel(t("exp_privacy_warning"))
        self._privacy.setWordWrap(True)
        self._privacy.setStyleSheet(f"color:{C['warn']};font-size:{FONT_BASE}px;")
        right.addWidget(self._privacy)
        self._estimate = QLabel()
        self._estimate.setStyleSheet(f"color:{C['text_dim']};font-size:{FONT_BASE}px;")
        right.addWidget(self._estimate)
        right.addStretch()

        bottom = QHBoxLayout()
        outer.addLayout(bottom)
        self._btn_start = QPushButton(t("btn_start"))
        self._btn_start.setObjectName("btn_start")
        self._btn_start.setFixedHeight(52)
        bottom.addWidget(self._btn_start)
        bottom.addStretch()
        self._btn_reset = QPushButton(t("exp_btn_reset"))
        configure_action_btn(self._btn_reset, 200)
        self._btn_reset.clicked.connect(self._reset_settings)
        bottom.addWidget(self._btn_reset)
        self._btn_generate = QPushButton(t("exp_btn_generate"))
        configure_action_btn(self._btn_generate, 160)
        self._btn_generate.clicked.connect(self._generate)
        bottom.addWidget(self._btn_generate)
        self._select_format("JSON")
        self.refresh()
        i18n.language_changed.connect(self.retranslate)

    def refresh(self):
        while self._history_layout.count():
            item = self._history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._history_rows.clear()
        if self._service is not None:
            for study in self._service.list_studies():
                patient = self._service._repositories.patients.get(study.patient_id)
                row = _StudyRow(study, patient, self._update_estimate)
                self._history_layout.addWidget(row)
                self._history_rows.append(row)
        if not self._history_rows:
            empty = QLabel(t("exp_no_studies"))
            empty.setObjectName("export_empty")
            empty.setStyleSheet(f"color:{C['text_dim']};")
            self._history_layout.addWidget(empty)
        self._update_estimate()

    def selected_study_ids(self) -> tuple[UUID, ...]:
        return tuple(row.study_id for row in self._history_rows if row.checkbox.isChecked())

    def selected_categories(self) -> tuple[str, ...]:
        return tuple(key for key, value in self._category_checks.items() if value.isChecked())

    def _select_format(self, fmt: str):
        self._active_fmt = fmt
        for name, button in self._fmt_btns.items():
            button.setProperty("active", "true" if name == fmt else "false")
            button.style().unpolish(button)
            button.style().polish(button)

    def _update_estimate(self):
        if self._service is None:
            self._estimate.setText("")
            return
        try:
            estimate = self._service.estimate(self.selected_study_ids(), self.selected_categories())
            self._estimate.setText(t("exp_estimate").format(
                count=estimate.study_count,
                size=_human_size(estimate.estimated_bytes),
            ))
            self._privacy.setVisible(estimate.contains_personal_data)
        except ExportError:
            self._estimate.setText(t("exp_selection_error"))

    def _reset_settings(self):
        self._select_format("JSON")
        for row in self._history_rows:
            row.checkbox.setChecked(False)
        for name, checkbox in self._category_checks.items():
            checkbox.setChecked(name != "raw_data")

    def _generate(self):
        if self._service is None:
            return
        directory = QFileDialog.getExistingDirectory(self, t("exp_btn_generate"), str(self._default_directory))
        if not directory:
            return
        try:
            result = self._service.export(directory, self._active_fmt, self.selected_study_ids(), self.selected_categories())
        except (ExportError, OSError):
            QMessageBox.warning(
                self, t("study_action_error_title"), t("exp_generation_error")
            )
            technical_event(_logger, logging.ERROR, "export.failed", export_format=self._active_fmt.lower(), result="failed")
            return
        technical_event(_logger, logging.INFO, "export.completed", export_format=self._active_fmt.lower(), result="success")
        QMessageBox.information(
            self, t("exp_btn_generate"), t("exp_saved").format(path=result.directory)
        )

    def retranslate(self):
        self._box_format.retranslate()
        self._box_categories.retranslate()
        self._box_history.retranslate()
        for category, checkbox in self._category_checks.items():
            checkbox.setText(t(_CATEGORY_LABELS[category]))
        self._privacy.setText(t("exp_privacy_warning"))
        empty = self.findChild(QLabel, "export_empty")
        if empty is not None:
            empty.setText(t("exp_no_studies"))
        for row in self._history_rows:
            row.retranslate()
        self._update_estimate()
        self._btn_start.setText(t("btn_start"))
        self._btn_reset.setText(t("exp_btn_reset"))
        self._btn_generate.setText(t("exp_btn_generate"))


def _human_size(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if amount < 1024 or unit == "GB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} ГБ"
