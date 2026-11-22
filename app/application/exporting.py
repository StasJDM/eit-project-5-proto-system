"""Versioned, deterministic export of persisted EIT studies."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import csv
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import UUID
from xml.etree import ElementTree
from xml.parsers.expat import ParserCreate
from xml.sax.saxutils import escape
import zipfile

from ..data_sources.json_contract import RawMeasurementFrame
from ..domain import EITFrame, serialize_model
from ..storage import AcquisitionRecordingStore, RecordingError, RepositoryBundle


EXPORT_SCHEMA_VERSION = "eit-export-1.0.0"
CSV_ENCODING = "utf-8-sig"
CSV_DELIMITER = ";"
EXCEL_MAX_ROWS = 1_048_576
EXPORT_CATEGORIES = ("metadata", "metrics", "trends", "events", "raw_data")


class ExportError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExportEstimate:
    study_count: int
    estimated_bytes: int
    contains_personal_data: bool


@dataclass(frozen=True, slots=True)
class ExportResult:
    directory: Path
    files: tuple[Path, ...]
    manifest_path: Path


class StudyExportService:
    def __init__(
        self,
        repositories: RepositoryBundle,
        recording_store: AcquisitionRecordingStore | None = None,
    ) -> None:
        self._repositories = repositories
        self._recording_store = recording_store

    def list_studies(self):
        return tuple(self._repositories.studies.list_all())

    def estimate(
        self, study_ids: Iterable[UUID], categories: Iterable[str]
    ) -> ExportEstimate:
        ids = tuple(dict.fromkeys(study_ids))
        selected = _categories(categories)
        total = 0
        for study_id in ids:
            study = self._required_study(study_id)
            if "metadata" in selected:
                patient = self._repositories.patients.get(study.patient_id)
                total += len(_json_bytes({
                    "study": serialize_model(study),
                    "patient": serialize_model(patient) if patient else None,
                }))
            if "events" in selected:
                total += sum(len(_json_bytes(serialize_model(item))) for item in self._repositories.events.list_for_study(study_id))
            if selected & {"metrics", "trends"}:
                total += sum(len(_json_bytes(serialize_model(item))) for item in self._all_trends(study_id))
            if "raw_data" in selected:
                total += self._recording_size(study_id)
        return ExportEstimate(len(ids), total, "metadata" in selected)

    def export(
        self,
        destination: Path | str,
        export_format: str,
        study_ids: Sequence[UUID],
        categories: Iterable[str],
        *,
        now_utc: datetime | None = None,
    ) -> ExportResult:
        if not study_ids:
            raise ExportError("at least one study must be selected")
        selected = _categories(categories)
        if not selected:
            raise ExportError("at least one export category must be selected")
        fmt = export_format.strip().lower()
        if fmt not in {"json", "csv", "excel", "xlsx"}:
            raise ExportError(f"unsupported export format: {export_format}")
        now = now_utc or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ExportError("export timestamp must be timezone-aware")
        studies = tuple(self._required_study(item) for item in dict.fromkeys(study_ids))
        root = Path(destination)
        root.mkdir(parents=True, exist_ok=True)
        package_name = "eit_export_" + now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = root / package_name
        temporary = Path(tempfile.mkdtemp(prefix=f".{package_name}-", dir=root))
        try:
            with tempfile.TemporaryDirectory(dir=temporary) as scratch:
                payload = self._build_payload(studies, selected, now, Path(scratch))
                if fmt == "json":
                    generated = [self._write_json(temporary, payload)]
                elif fmt == "csv":
                    generated = self._write_csv(temporary, payload, selected)
                else:
                    generated = [self._write_xlsx(temporary, payload, selected)]
            manifest = {
                "schema_version": EXPORT_SCHEMA_VERSION,
                "created_at_utc": now.astimezone(timezone.utc).isoformat(),
                "format": "xlsx" if fmt in {"excel", "xlsx"} else fmt,
                "study_ids": [str(item.id) for item in studies],
                "categories": sorted(selected),
                "files": [
                    {"name": path.name, "size_bytes": path.stat().st_size, "sha256": _sha256(path)}
                    for path in generated
                ],
            }
            manifest_path = temporary / "manifest.json"
            _atomic_write(manifest_path, _json_bytes(manifest, pretty=True))
            os.replace(temporary, target)
        except Exception:
            for child in temporary.glob("*"):
                child.unlink(missing_ok=True)
            temporary.rmdir()
            raise
        files = tuple(target / item.name for item in generated)
        return ExportResult(target, files, target / "manifest.json")

    def _required_study(self, study_id: UUID):
        study = self._repositories.studies.get(study_id)
        if study is None:
            raise ExportError(f"study not found: {study_id}")
        return study

    def _all_trends(self, study_id: UUID):
        bounds = self._repositories.trends.bounds(study_id)
        if bounds is None:
            return ()
        interval = self._repositories.trends.list_range(study_id, *bounds, aggregation_kind="interval")
        cycles = self._repositories.trends.list_range(study_id, *bounds, aggregation_kind="breath_cycle")
        return tuple(sorted((*interval, *cycles), key=lambda item: (item.interval_start_utc, str(item.id))))

    def _recording_size(self, study_id: UUID) -> int:
        if self._recording_store is None:
            return 0
        directory = self._recording_store.root / str(study_id)
        return sum(path.stat().st_size for path in directory.glob("**/*") if path.is_file())

    def _stage_raw_frames(self, study_id, session, scratch):
        # A damaged later chunk invalidates the entire raw-data section.
        # Stage one JSON object per line so no partial recording escapes.
        path = scratch / str(study_id)
        with path.open("wb") as output:
            if self._recording_store is not None and session is not None:
                try:
                    for _, frames in self._recording_store.iter_chunks(study_id, session.id):
                        for frame in frames:
                            row = _raw_frame_data(frame)
                            output.write(json.dumps(row, ensure_ascii=False,
                                                    separators=(",", ":")).encode("utf-8"))
                            output.write(b"\n")
                except (FileNotFoundError, RecordingError):
                    output.truncate(0)
        return path

    def _build_payload(self, studies, selected: set[str], now: datetime, scratch: Path):
        entries = []
        for study in studies:
            session = self._repositories.sessions.get_for_study(study.id)
            trends = self._all_trends(study.id) if selected & {"metrics", "trends"} else ()
            entry: dict[str, Any] = {"study_id": str(study.id)}
            if "metadata" in selected:
                patient = self._repositories.patients.get(study.patient_id)
                entry["metadata"] = {
                    "patient": serialize_model(patient) if patient else None,
                    "study": serialize_model(study),
                    "session": serialize_model(session) if session else None,
                }
            if "metrics" in selected:
                entry["metrics"] = _metric_rows(study.id, trends)
            if "trends" in selected:
                entry["trends"] = [serialize_model(item) for item in trends]
            if "events" in selected:
                entry["events"] = [
                    serialize_model(item)
                    for item in self._repositories.events.list_for_study(study.id)
                ]
            if "raw_data" in selected:
                entry["raw_data"] = self._stage_raw_frames(study.id, session, scratch)
            entries.append(entry)
        return {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "created_at_utc": now.astimezone(timezone.utc).isoformat(),
            "categories": sorted(selected),
            "studies": entries,
        }

    @staticmethod
    def _write_json(directory: Path, payload: Mapping[str, Any]) -> Path:
        path = directory / "data.json"
        with path.open("wb") as output:
            header = {key: value for key, value in payload.items() if key != "studies"}
            output.write(_json_bytes(header)[:-1] + b',"studies":[')
            for index, entry in enumerate(payload["studies"]):
                if index:
                    output.write(b",")
                metadata = {key: value for key, value in entry.items() if key != "raw_data"}
                output.write(_json_bytes(metadata)[:-1])
                if "raw_data" in entry:
                    output.write(b',"raw_data":[')
                    with entry["raw_data"].open("rb") as rows:
                        for number, line in enumerate(rows):
                            if number:
                                output.write(b",")
                            output.write(line)
                    output.write(b"]")
                output.write(b"}")
            output.write(b"]}")
            output.flush()
            os.fsync(output.fileno())
        return path

    @staticmethod
    def _write_csv(directory: Path, payload: Mapping[str, Any], selected: set[str]) -> list[Path]:
        paths = []
        for name in EXPORT_CATEGORIES:
            if name not in selected:
                continue
            path = directory / f"{name}.csv"
            with path.open("w", encoding=CSV_ENCODING, newline="") as output:
                rows = _table_rows(payload, name)
                for columns, batch in _table_batches(rows, limit=None, directory=directory):
                    writer = csv.DictWriter(output, fieldnames=columns, delimiter=CSV_DELIMITER,
                                            lineterminator="\r\n")
                    writer.writeheader()
                    writer.writerows({key: _csv_value(row.get(key)) for key in columns}
                                     for row in batch)
                output.flush()
                os.fsync(output.fileno())
            paths.append(path)
        return paths

    @staticmethod
    def _write_xlsx(directory: Path, payload: Mapping[str, Any], selected: set[str]) -> Path:
        path = directory / "data.xlsx"
        _write_workbook(path, payload, selected)
        validate_xlsx(path)
        return path


def validate_xlsx(path: Path | str) -> None:
    with zipfile.ZipFile(path) as archive:
        required = {"[Content_Types].xml", "xl/workbook.xml", "xl/styles.xml"}
        if not required.issubset(archive.namelist()):
            raise ExportError("invalid xlsx structure")
        ElementTree.fromstring(archive.read("xl/workbook.xml"))
        for name in archive.namelist():
            if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                with archive.open(name) as sheet:
                    # Validate well-formed XML without retaining the worksheet tree.
                    ParserCreate().ParseFile(sheet)


def _categories(values: Iterable[str]) -> set[str]:
    selected = {str(item).strip().lower() for item in values}
    unknown = selected - set(EXPORT_CATEGORIES)
    if unknown:
        raise ExportError("unknown export categories: " + ", ".join(sorted(unknown)))
    return selected


def _metric_rows(study_id: UUID, trends) -> list[dict[str, Any]]:
    interval = [item for item in trends if item.aggregation_kind == "interval"]
    if not interval:
        return []
    values = lambda attr: [getattr(item, attr) for item in interval if getattr(item, attr) is not None]
    result: dict[str, Any] = {"study_id": str(study_id), "sample_intervals": len(interval)}
    for attr in ("global_value", "right_value", "left_value", "respiratory_rate_bpm"):
        items = values(attr)
        result[f"{attr}_mean"] = sum(items) / len(items) if items else None
    roi_count = max((len(item.roi_values) for item in interval), default=0)
    for index in range(roi_count):
        items = [
            item.roi_values[index] for item in interval
            if index < len(item.roi_values) and item.roi_values[index] is not None
        ]
        result[f"roi_{index + 1}_mean"] = sum(items) / len(items) if items else None
    result["algorithm_versions"] = sorted({item.algorithm_version for item in interval})
    return [result]


def _raw_frame_data(frame) -> dict[str, Any]:
    if isinstance(frame, EITFrame):
        return serialize_model(frame)
    if isinstance(frame, RawMeasurementFrame):
        return {
            "model_type": "RawMeasurementFrame",
            "sequence_number": frame.sequence_number,
            "timestamp_utc": frame.timestamp_utc.isoformat(),
            "protocol_id": frame.protocol_id,
            "belt_index": frame.belt_index,
            "quality": frame.quality.value,
            "timestamp_source": frame.timestamp_source.value,
            "simulated": frame.simulated,
            "channel_values": list(frame.channel_values),
        }
    raise ExportError(f"unsupported raw frame type: {type(frame).__name__}")


def _table_rows(payload, name):
    for entry in payload["studies"]:
        study_id = entry["study_id"]
        if name == "metadata":
            yield {"study_id": study_id, **_flatten(entry["metadata"])}
        elif name == "raw_data":
            with entry[name].open("rb") as rows:
                for line in rows:
                    yield {"study_id": study_id, **_flatten(json.loads(line))}
        else:
            for value in entry[name]:
                yield {"study_id": study_id, **_flatten(value)}


def _table_batches(rows, *, limit, directory):
    """Discover the ordered union of columns for each CSV or Excel sheet."""
    first = True
    while True:
        with tempfile.SpooledTemporaryFile(max_size=1024 * 1024, dir=directory) as spool:
            columns = {}
            count = 0
            for row in islice(rows, limit):
                columns.update(dict.fromkeys(row))
                spool.write(_json_bytes(row) + b"\n")
                count += 1
            if count or first:
                spool.seek(0)
                yield list(columns) or ["study_id"], (json.loads(line) for line in spool)
            if limit is None or count < limit:
                return
            first = False


def _flatten(value: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(item, Mapping):
            result.update(_flatten(item, name))
        elif isinstance(item, (list, tuple)):
            result[name] = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        else:
            result[name] = item
    return result


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".15g")
    return value


def _json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    ).encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    except Exception:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_workbook(path: Path, payload, selected) -> None:
    # The export directory is published atomically after validation.
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as book:
        titles = []
        for name in EXPORT_CATEGORIES:
            if name not in selected:
                continue
            first_sheet = len(titles)
            for columns, batch in _table_batches(_table_rows(payload, name),
                                                  limit=EXCEL_MAX_ROWS - 1, directory=path.parent):
                titles.append(name)
                with book.open(f"xl/worksheets/sheet{len(titles)}.xml", "w", force_zip64=True) as sheet:
                    sheet.write(b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>')
                    sheet.write(_xlsx_row(1, columns, header=True).encode("utf-8"))
                    last = 1
                    for last, row in enumerate(batch, 2):
                        values = [row.get(column) for column in columns]
                        sheet.write(_xlsx_row(last, values).encode("utf-8"))
                    cell = _column_name(len(columns)) + str(last)
                    sheet.write(f'</sheetData><autoFilter ref="A1:{cell}"/></worksheet>'.encode())
            if len(titles) - first_sheet > 1:
                for index in range(first_sheet, len(titles)):
                    titles[index] = f"{name[:28]}_{index - first_sheet + 1}"[:31]
        overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(titles) + 1)
        )
        book.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + overrides + '</Types>')
        book.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        sheet_refs = "".join(f'<sheet name="{escape(title)}" sheetId="{i}" r:id="rId{i}"/>' for i, title in enumerate(titles, 1))
        book.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + sheet_refs + '</sheets></workbook>')
        rels = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(titles) + 1))
        rels += f'<Relationship Id="rId{len(titles)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        book.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + rels + '</Relationships>')
        book.writestr("xl/styles.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><name val="Arial"/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf fontId="0" fillId="0" borderId="0"/><xf fontId="1" fillId="0" borderId="0" applyFont="1"/></cellXfs></styleSheet>')


def _xlsx_row(number: int, values: Sequence[Any], *, header: bool = False) -> str:
    cells = []
    for index, value in enumerate(values, 1):
        ref = f"{_column_name(index)}{number}"
        style = ' s="1"' if header else ""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            cells.append(f'<c r="{ref}"{style}><v>{value}</v></c>')
        else:
            text = "" if value is None else _csv_value(value)
            cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t>{escape(str(text))}</t></is></c>')
    return f'<row r="{number}">' + "".join(cells) + '</row>'


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result
