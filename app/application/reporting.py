"""Reproducible medical-report snapshots built only from persisted data."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from statistics import mean
import tempfile
from typing import Any
from uuid import UUID

from ..domain import Report, ReportStatus, serialize_model
from ..storage import RepositoryBundle


REPORT_TEMPLATE_VERSION = "eit-medical-report-1.0.0"


class ReportError(RuntimeError):
    pass


class MedicalReportService:
    def __init__(self, repositories: RepositoryBundle, output_dir: Path | str = "exports/reports") -> None:
        self._repositories = repositories
        self.output_dir = Path(output_dir)

    def list_reports(self):
        return tuple(self._repositories.reports.list_all())

    def studies(self):
        return tuple(self._repositories.studies.list_all())

    def create(
        self,
        study_id: UUID,
        period_start_utc: datetime,
        period_end_utc: datetime,
        *,
        title: str,
        language: str = "ru",
        created_at_utc: datetime | None = None,
    ) -> Report:
        start = _utc(period_start_utc, "period_start_utc")
        end = _utc(period_end_utc, "period_end_utc")
        if end < start:
            raise ReportError("report period end precedes start")
        if not title.strip():
            raise ReportError("report title must not be blank")
        study = self._repositories.studies.get(study_id)
        if study is None:
            raise ReportError("study not found")
        patient = self._repositories.patients.get(study.patient_id)
        if patient is None:
            raise ReportError("study patient not found")
        session = self._repositories.sessions.get_for_study(study_id)
        if session is not None and session.started_at_utc is not None:
            session_end = session.ended_at_utc or study.updated_at_utc
            if end < session.started_at_utc or start > session_end:
                raise ReportError("report period does not overlap the study session")
        trends = tuple(self._repositories.trends.list_range(study_id, start, end, aggregation_kind="interval"))
        cycles = tuple(self._repositories.trends.list_range(study_id, start, end, aggregation_kind="breath_cycle"))
        events = tuple(self._repositories.events.search(study_id, start_utc=start, end_utc=end))
        now = _utc(created_at_utc or datetime.now(timezone.utc), "created_at_utc")
        algorithms = tuple(sorted({item.algorithm_version for item in (*trends, *cycles)})) or ("no-persisted-algorithm",)
        snapshot = {
            "template_version": REPORT_TEMPLATE_VERSION,
            "created_at_utc": now.isoformat(),
            "language": language,
            "title": title.strip(),
            "patient": serialize_model(patient),
            "study": serialize_model(study),
            "session": serialize_model(session) if session else None,
            "period_start_utc": start.isoformat(),
            "period_end_utc": end.isoformat(),
            "summary": _summary(trends),
            "breathing": {
                "type": "undetermined",
                "reason": "validated_classifier_not_configured",
            },
            "trends": [serialize_model(item) for item in trends],
            "breath_cycles": [serialize_model(item) for item in cycles],
            "events": [serialize_model(item) for item in events],
        }
        report = Report(
            study_id=study_id,
            period_start_utc=start,
            period_end_utc=end,
            status=ReportStatus.GENERATED,
            template_version=REPORT_TEMPLATE_VERSION,
            algorithm_versions=algorithms,
            created_at_utc=now,
            title=title.strip(),
            snapshot_json=json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            simulated=study.simulated,
        )
        self._repositories.reports.save(report)
        return report

    def snapshot(self, report: Report | UUID) -> dict[str, Any]:
        value = self._repositories.reports.get(report) if isinstance(report, UUID) else report
        if value is None or value.snapshot_json is None:
            raise ReportError("report snapshot is unavailable")
        return json.loads(value.snapshot_json)

    def render_text(self, report: Report | UUID) -> str:
        snapshot = self.snapshot(report)
        patient = snapshot["patient"]
        summary = snapshot["summary"]
        full_name = " ".join(filter(None, (
            patient.get("family_name"), patient.get("given_name"), patient.get("middle_name")
        ))) or patient.get("external_id") or "—"
        lines = [
            snapshot["title"],
            f"Пациент: {full_name}",
            f"ID исследования: {snapshot['study']['id']}",
            f"Период: {snapshot['period_start_utc']} — {snapshot['period_end_utc']}",
            "",
            "Показатели:",
            f"RR: {_display(summary.get('respiratory_rate_bpm_mean'))} вд/мин",
            f"Глобальная аэрация: {_display(summary.get('global_value_mean'))} а.е.",
            f"R/L: {_display(summary.get('right_left_ratio'))}",
            f"Тип дыхания: {snapshot['breathing']['type']}",
            "ROI: " + ", ".join(_display(value) for value in summary.get("roi_means", [])),
            "",
            "События:",
        ]
        if snapshot["events"]:
            lines.extend(
                f"{event['occurred_at_utc']} [{event['event_type']}] {event['text']} ({event['author']})"
                for event in snapshot["events"]
            )
        else:
            lines.append("Нет зарегистрированных событий")
        return "\n".join(lines)

    def render_html(self, report: Report | UUID) -> str:
        snapshot = self.snapshot(report)
        language = snapshot.get("language", "ru")
        labels = _REPORT_LABELS.get(language, _REPORT_LABELS["ru"])
        patient = snapshot["patient"]
        summary = snapshot["summary"]
        name = " ".join(filter(None, (
            patient.get("family_name"), patient.get("given_name"), patient.get("middle_name")
        ))) or patient.get("external_id") or "—"
        roi_rows = "".join(
            f"<tr><td>ROI {index}</td><td>{_display(value)}</td><td>a.u.</td></tr>"
            for index, value in enumerate(summary.get("roi_means", []), 1)
        )
        event_rows = "".join(
            "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                _html(event["occurred_at_utc"]), _html(event["event_type"]), _html(event["text"])
            )
            for event in snapshot["events"]
        ) or f'<tr><td colspan="3">{labels["no_events"]}</td></tr>'
        return f"""<!doctype html><html><head><meta charset="utf-8"><style>
body {{ font-family: Arial, sans-serif; font-size: 10pt; color:#162235; }}
h1 {{ color:#123f70; font-size:18pt; margin:0 0 12px 0; }}
h2 {{ color:#123f70; font-size:12pt; margin:16px 0 6px 0; }}
table {{ border-collapse:collapse; width:100%; margin:4px 0 10px 0; }}
th,td {{ border:1px solid #b8c2cc; padding:5px; vertical-align:top; }}
th {{ background:#eaf1f8; text-align:left; }} .muted {{ color:#5f6b78; }}
</style></head><body>
<h1>{_html(snapshot['title'])}</h1>
<table><tr><th>{labels['patient']}</th><td>{_html(name)}</td></tr>
<tr><th>{labels['study_id']}</th><td>{_html(snapshot['study']['id'])}</td></tr>
<tr><th>{labels['period']}</th><td>{_html(snapshot['period_start_utc'])}<br>{_html(snapshot['period_end_utc'])}</td></tr></table>
<h2>{labels['metrics']}</h2><table><tr><th>{labels['metric']}</th><th>{labels['value']}</th><th>{labels['unit']}</th></tr>
<tr><td>RR</td><td>{_display(summary.get('respiratory_rate_bpm_mean'))}</td><td>bpm</td></tr>
<tr><td>Global aeration</td><td>{_display(summary.get('global_value_mean'))}</td><td>a.u.</td></tr>
<tr><td>R/L</td><td>{_display(summary.get('right_left_ratio'))}</td><td></td></tr>
<tr><td>{labels['breathing']}</td><td>{_html(snapshot['breathing']['type'])}</td><td></td></tr>{roi_rows}</table>
<h2>{labels['trends']}</h2><p>{labels['intervals']}: {summary.get('interval_count', 0)}. 
{labels['quality']}: {_html(json.dumps(summary.get('quality_counts', {}), ensure_ascii=False))}</p>
<h2>{labels['events']}</h2><table><tr><th>UTC</th><th>{labels['type']}</th><th>{labels['description']}</th></tr>{event_rows}</table>
</body></html>"""

    def generate_pdf(
        self,
        report: Report | UUID,
        destination: Path | str | None = None,
        *,
        software_version: str = "EIT prototype",
    ) -> Report:
        value = self._repositories.reports.get(report) if isinstance(report, UUID) else report
        if value is None:
            raise ReportError("report not found")
        target = Path(destination) if destination is not None else self.output_dir / f"report_{value.id}.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}-", suffix=".pdf", dir=target.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            _write_pdf(
                temporary, self.render_html(value), study_id=str(value.study_id),
                created_at=value.created_at_utc, software_version=software_version,
                page_label=_REPORT_LABELS.get(
                    self.snapshot(value).get("language", "ru"), _REPORT_LABELS["ru"]
                )["page"],
            )
            if temporary.stat().st_size == 0:
                raise ReportError("generated PDF is empty")
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        return self.attach_file(value, str(target), digest)

    def attach_file(self, report: Report, file_name: str, checksum_sha256: str) -> Report:
        updated = replace(report, file_name=file_name, checksum_sha256=checksum_sha256)
        self._repositories.reports.save(updated)
        return updated


def _summary(trends) -> dict[str, Any]:
    def average(name):
        values = [getattr(item, name) for item in trends if getattr(item, name) is not None]
        return mean(values) if values else None
    right = average("right_value")
    left = average("left_value")
    roi = []
    roi_count = max((len(item.roi_values) for item in trends), default=0)
    for index in range(roi_count):
        values = [
            item.roi_values[index] for item in trends
            if index < len(item.roi_values) and item.roi_values[index] is not None
        ]
        roi.append(mean(values) if values else None)
    return {
        "interval_count": len(trends),
        "global_value_mean": average("global_value"),
        "right_value_mean": right,
        "left_value_mean": left,
        "right_left_ratio": right / left if right is not None and left not in (None, 0) else None,
        "respiratory_rate_bpm_mean": average("respiratory_rate_bpm"),
        "roi_means": roi,
        "quality_counts": {
            quality: sum(item.quality.value == quality for item in trends)
            for quality in ("valid", "degraded", "stale", "unavailable")
        },
    }


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None:
        raise ReportError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _display(value) -> str:
    return "—" if value is None else format(value, ".4g")


def _html(value: Any) -> str:
    import html
    return html.escape(str(value))


_REPORT_LABELS = {
    "ru": {"patient":"Пациент","study_id":"ID исследования","period":"Период","metrics":"Показатели","metric":"Показатель","value":"Значение","unit":"Единица","breathing":"Тип дыхания","trends":"Тренды","intervals":"Интервалов","quality":"Качество","events":"События","type":"Тип","description":"Описание","no_events":"Нет зарегистрированных событий","page":"Страница"},
    "en": {"patient":"Patient","study_id":"Study ID","period":"Period","metrics":"Metrics","metric":"Metric","value":"Value","unit":"Unit","breathing":"Breathing type","trends":"Trends","intervals":"Intervals","quality":"Quality","events":"Events","type":"Type","description":"Description","no_events":"No recorded events","page":"Page"},
    "zh": {"patient":"患者","study_id":"检查 ID","period":"期间","metrics":"指标","metric":"指标","value":"值","unit":"单位","breathing":"呼吸类型","trends":"趋势","intervals":"间隔","quality":"质量","events":"事件","type":"类型","description":"描述","no_events":"无记录事件","page":"页"},
    "vi": {"patient":"Bệnh nhân","study_id":"ID nghiên cứu","period":"Khoảng thời gian","metrics":"Chỉ số","metric":"Chỉ số","value":"Giá trị","unit":"Đơn vị","breathing":"Kiểu thở","trends":"Xu hướng","intervals":"Khoảng","quality":"Chất lượng","events":"Sự kiện","type":"Loại","description":"Mô tả","no_events":"Không có sự kiện","page":"Trang"},
}


def _write_pdf(path: Path, html_text: str, *, study_id: str, created_at: datetime, software_version: str, page_label: str) -> None:
    from PySide6.QtCore import QMarginsF, QRectF, QSizeF
    from PySide6.QtGui import QFont, QFontDatabase, QPageLayout, QPageSize, QPainter, QPdfWriter, QTextDocument

    writer = QPdfWriter(str(path))
    writer.setResolution(144)
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setPageMargins(QMarginsF(15, 15, 15, 18), QPageLayout.Millimeter)
    writer.setTitle("EIT medical report")
    writer.setCreator(software_version)
    paint_rect = writer.pageLayout().paintRectPixels(writer.resolution())
    footer_height = 34.0
    content_height = float(paint_rect.height()) - footer_height
    document = QTextDocument()
    families = set(QFontDatabase.families())
    family = "Arial" if "Arial" in families else "Sans Serif"
    document.setDefaultFont(QFont(family, 10))
    document.setHtml(html_text)
    document.setPageSize(QSizeF(float(paint_rect.width()), content_height))
    page_count = max(1, document.pageCount())
    painter = QPainter(writer)
    if not painter.isActive():
        raise ReportError("cannot initialize PDF painter")
    try:
        for page in range(page_count):
            if page:
                writer.newPage()
            painter.save()
            painter.translate(float(paint_rect.left()), float(paint_rect.top()) - page * content_height)
            document.drawContents(
                painter,
                QRectF(0.0, page * content_height, float(paint_rect.width()), content_height),
            )
            painter.restore()
            footer = (
                f"{created_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  |  "
                f"{software_version}  |  {study_id}  |  {page_label} {page + 1}/{page_count}"
            )
            painter.drawText(
                QRectF(float(paint_rect.left()), float(paint_rect.top()) + content_height + 6,
                       float(paint_rect.width()), footer_height - 6),
                int(0x0081), footer,
            )
    finally:
        painter.end()
