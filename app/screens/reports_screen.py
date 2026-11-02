"""Creation and preview of reproducible reports from persisted studies."""

from __future__ import annotations

from datetime import timezone

from PySide6.QtCore import QDateTime, QTimeZone, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QDateTimeEdit, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QStackedWidget, QTextEdit,
    QVBoxLayout, QWidget,
)
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter

from ..application.reporting import MedicalReportService, ReportError
from ..i18n import i18n, t
from ..styles import C, FONT_BASE, FONT_TITLE, configure_action_btn, yellow_btn_style


class _SectionBox(QWidget):
    def __init__(self, title_key, parent=None):
        super().__init__(parent)
        self._title_key = title_key
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QWidget()
        header.setFixedHeight(32)
        header.setStyleSheet(f"background:{C['blue_dark']};border:1px solid {C['border']};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 0, 10, 0)
        self._title = QLabel(t(title_key))
        self._title.setStyleSheet(f"color:white;font-size:{FONT_TITLE}px;font-weight:bold;")
        header_layout.addWidget(self._title)
        root.addWidget(header)
        body = QWidget()
        body.setStyleSheet(f"background:{C['bg_panel']};border:1px solid {C['border']};")
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(10, 10, 10, 10)
        root.addWidget(body)

    def retranslate(self):
        self._title.setText(t(self._title_key))


class _ReportRow(QWidget):
    def __init__(self, report, patient_name, on_view, on_print, parent=None):
        super().__init__(parent)
        self.report = report
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        self._patient_name = patient_name
        self._text = QLabel()
        self._text.setStyleSheet(f"color:{C['text']};font-size:{FONT_BASE}px;")
        layout.addWidget(self._text, 1)
        self._view = QPushButton(t("rep_btn_view"))
        self._view.clicked.connect(lambda: on_view(report))
        layout.addWidget(self._view)
        self._print = QPushButton(t("rep_btn_print"))
        self._print.clicked.connect(lambda: on_print(report))
        layout.addWidget(self._print)
        self.setStyleSheet(f"background:{C['bg_card']};border:1px solid {C['border']};")
        self.retranslate()

    def retranslate(self):
        title = self.report.title or t("rep_default_title")
        created = self.report.created_at_utc.astimezone().strftime("%d.%m.%Y %H:%M")
        self._text.setText(f"{title}\n{self._patient_name} · {created}")
        self._view.setText(t("rep_btn_view"))
        self._print.setText(t("rep_btn_print"))


class ReportsScreen(QWidget):
    def __init__(self, report_service: MedicalReportService | None = None, parent=None):
        super().__init__(parent)
        self._service = report_service
        self._selected_report = None
        self._rows: list[_ReportRow] = []
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
        columns.addLayout(left, 38)
        self._box_list = _SectionBox("rep_saved_reports")
        self._list_layout = self._box_list.body_layout
        self._btn_new = QPushButton(t("rep_new_btn"))
        self._btn_new.setStyleSheet(yellow_btn_style())
        self._btn_new.clicked.connect(self._new_report)
        self._list_layout.addWidget(self._btn_new)
        left.addWidget(self._box_list)
        left.addStretch()

        right = QVBoxLayout()
        columns.addLayout(right, 62)
        self._box_form = _SectionBox("rep_create_new")
        form = self._box_form.body_layout
        patient_row = QHBoxLayout()
        self._lbl_patient = QLabel(t("rep_patient") + ":")
        patient_row.addWidget(self._lbl_patient)
        self._combo_study = QComboBox()
        self._combo_study.currentIndexChanged.connect(self._sync_period)
        patient_row.addWidget(self._combo_study, 1)
        form.addLayout(patient_row)

        period = QHBoxLayout()
        self._lbl_period = QLabel(t("rep_period") + ":")
        period.addWidget(self._lbl_period)
        self._from = QDateTimeEdit()
        self._from.setDisplayFormat("dd.MM.yyyy HH:mm:ss")
        self._from.setTimeZone(QTimeZone.UTC)
        period.addWidget(self._from)
        self._to = QDateTimeEdit()
        self._to.setDisplayFormat("dd.MM.yyyy HH:mm:ss")
        self._to.setTimeZone(QTimeZone.UTC)
        period.addWidget(self._to)
        form.addLayout(period)

        name_row = QHBoxLayout()
        self._lbl_name = QLabel(t("rep_report_name") + ":")
        name_row.addWidget(self._lbl_name)
        self._name = QLineEdit()
        self._name.setPlaceholderText(t("rep_eit_study"))
        name_row.addWidget(self._name, 1)
        form.addLayout(name_row)
        self._btn_generate = QPushButton(t("rep_btn_generate"))
        self._btn_generate.setStyleSheet(yellow_btn_style())
        self._btn_generate.clicked.connect(self._generate)
        form.addWidget(self._btn_generate)
        right.addWidget(self._box_form)

        self._box_preview = _SectionBox("rep_preview_title")
        self._preview_stack = QStackedWidget()
        self._empty = QLabel(t("rep_preview_empty"))
        self._empty.setAlignment(Qt.AlignCenter)
        self._preview_stack.addWidget(self._empty)
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFont(QFont("DejaVu Sans Mono", FONT_BASE))
        self._preview_stack.addWidget(self._preview)
        self._box_preview.body_layout.addWidget(self._preview_stack)
        right.addWidget(self._box_preview, 1)

        bottom = QHBoxLayout()
        outer.addLayout(bottom)
        self._btn_start = QPushButton(t("btn_start"))
        self._btn_start.setObjectName("btn_start")
        self._btn_start.setFixedHeight(52)
        bottom.addWidget(self._btn_start)
        bottom.addStretch()
        self._btn_reset = QPushButton(t("rep_btn_reset"))
        configure_action_btn(self._btn_reset, 180)
        self._btn_reset.clicked.connect(self._new_report)
        bottom.addWidget(self._btn_reset)
        self._btn_print_bottom = QPushButton(t("rep_btn_print"))
        configure_action_btn(self._btn_print_bottom, 140)
        self._btn_print_bottom.clicked.connect(lambda: self._print_report(self._selected_report))
        bottom.addWidget(self._btn_print_bottom)
        self.refresh()
        i18n.language_changed.connect(self.retranslate)

    def refresh(self):
        self._combo_study.blockSignals(True)
        self._combo_study.clear()
        if self._service is not None:
            for study in self._service.studies():
                patient = self._service._repositories.patients.get(study.patient_id)
                name = _patient_name(patient)
                self._combo_study.addItem(f"{name} · {str(study.id)[:8]}", study.id)
        self._combo_study.blockSignals(False)
        self._refresh_rows()
        self._sync_period()

    def _refresh_rows(self):
        for row in self._rows:
            self._list_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        if self._service is None:
            return
        for report in self._service.list_reports():
            study = self._service._repositories.studies.get(report.study_id)
            patient = self._service._repositories.patients.get(study.patient_id) if study else None
            row = _ReportRow(report, _patient_name(patient), self._view, self._print_report)
            self._list_layout.addWidget(row)
            self._rows.append(row)

    def _sync_period(self):
        if self._service is None or self._combo_study.currentData() is None:
            return
        study = self._service._repositories.studies.get(self._combo_study.currentData())
        session = self._service._repositories.sessions.get_for_study(study.id)
        start = session.started_at_utc if session and session.started_at_utc else study.created_at_utc
        end = session.ended_at_utc if session and session.ended_at_utc else study.updated_at_utc
        self._from.setDateTime(QDateTime(start))
        self._to.setDateTime(QDateTime(max(start, end)))

    def _new_report(self):
        self._selected_report = None
        self._name.clear()
        self._preview.clear()
        self._preview_stack.setCurrentIndex(0)

    def _generate(self):
        if self._service is None or self._combo_study.currentData() is None:
            return
        title = self._name.text().strip() or t("rep_eit_study")
        try:
            report = self._service.create(
                self._combo_study.currentData(),
                self._from.dateTime().toPython().astimezone(timezone.utc),
                self._to.dateTime().toPython().astimezone(timezone.utc),
                title=title,
                language=i18n.lang,
            )
            report = self._service.generate_pdf(report)
        except Exception:
            QMessageBox.warning(
                self, t("study_action_error_title"), t("rep_generation_error")
            )
            return
        self._refresh_rows()
        self._view(report)

    def _view(self, report):
        if report is None or self._service is None:
            return
        self._selected_report = report
        try:
            self._preview.setPlainText(self._service.render_text(report))
        except ReportError:
            QMessageBox.warning(
                self, t("study_action_error_title"), t("rep_preview_error")
            )
            return
        self._preview_stack.setCurrentIndex(1)

    def _print_report(self, report):
        if report is None or self._service is None:
            return
        self._view(report)
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.Accepted:
            return
        try:
            document = QTextDocument()
            document.setHtml(self._service.render_html(report))
            document.print_(printer)
        except Exception:
            QMessageBox.warning(
                self, t("study_action_error_title"), t("rep_print_error")
            )

    def retranslate(self):
        self._box_list.retranslate()
        self._box_form.retranslate()
        self._box_preview.retranslate()
        self._btn_new.setText(t("rep_new_btn"))
        self._lbl_patient.setText(t("rep_patient") + ":")
        self._lbl_period.setText(t("rep_period") + ":")
        self._lbl_name.setText(t("rep_report_name") + ":")
        self._btn_generate.setText(t("rep_btn_generate"))
        self._empty.setText(t("rep_preview_empty"))
        self._btn_start.setText(t("btn_start"))
        self._btn_reset.setText(t("rep_btn_reset"))
        self._btn_print_bottom.setText(t("rep_btn_print"))
        self._name.setPlaceholderText(t("rep_eit_study"))
        for row in self._rows:
            row.retranslate()


def _patient_name(patient) -> str:
    if patient is None:
        return "—"
    return " ".join(filter(None, (patient.family_name, patient.given_name, patient.middle_name))) or patient.external_id or "—"


def _report_text(name: str, patient: str, date: str, events=()) -> str:
    """Compatibility formatter for callers that only have an event sequence."""
    lines = [name, f"Пациент: {patient}", f"Дата: {date}", "", "События:"]
    lines.extend(
        f"{event.occurred_at_utc.isoformat()} [{event.event_type}] {event.text} ({event.author})"
        for event in events
    )
    if not events:
        lines.append("Нет зарегистрированных событий")
    return "\n".join(lines)
