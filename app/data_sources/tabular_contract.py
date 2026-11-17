"""Import row-oriented 208-channel EIT recordings from CSV and XLSX."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path, PurePosixPath
import re
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from .base import TimestampSource
from .json_contract import (
    ADJACENT_16_PROTOCOL_ID,
    CHANNEL_COUNT,
    ELECTRODE_COUNT,
    JSONMeasurementRecording,
    RawMeasurementFrame,
)


class TabularMeasurementFormatError(ValueError):
    """A CSV/XLSX file is not a row-oriented 208-channel recording."""


_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CELL_REFERENCE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")


def load_tabular_measurement_recording(
    path: str | Path,
    *,
    fallback_frame_rate_hz: float = 25.0,
    recording_started_at_utc: datetime | None = None,
    simulated: bool = False,
) -> JSONMeasurementRecording:
    """Load one frame per row, dropping blank and completely zero rows."""
    source_path = Path(path)
    suffix = source_path.suffix.lower()
    try:
        rows = _read_csv_rows(source_path) if suffix == ".csv" else _read_xlsx_rows(source_path)
        modified = datetime.fromtimestamp(source_path.stat().st_mtime, tz=timezone.utc)
    except TabularMeasurementFormatError:
        raise
    except (OSError, UnicodeError, csv.Error, BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise TabularMeasurementFormatError(
            f"cannot read EIT {suffix.removeprefix('.').upper()} file: {exc}"
        ) from exc

    rate = _positive_frame_rate(fallback_frame_rate_hz)
    start = _utc(recording_started_at_utc or modified)
    frames: list[RawMeasurementFrame] = []
    for row_number, cells in rows:
        values = _numeric_row(cells, row_number)
        if values is None:
            continue
        if len(values) != CHANNEL_COUNT:
            raise TabularMeasurementFormatError(
                f"row {row_number} has {len(values)} values; expected {CHANNEL_COUNT}"
            )
        if all(value == 0.0 for value in values):
            continue
        sequence = len(frames)
        frames.append(RawMeasurementFrame(
            sequence_number=sequence,
            timestamp_utc=start + timedelta(seconds=sequence / rate),
            channel_values=values,
            timestamp_source=TimestampSource.SYNTHESIZED,
            simulated=simulated,
        ))
    if not frames:
        raise TabularMeasurementFormatError("recording contains no non-zero frames")

    return JSONMeasurementRecording(
        frames=tuple(frames),
        frame_rate_hz=rate,
        frame_rate_source="fallback",
        electrode_count=ELECTRODE_COUNT,
        channel_count=CHANNEL_COUNT,
        protocol_id=ADJACENT_16_PROTOCOL_ID,
        excitation_frequency_khz=None,
        excitation_current_ma=None,
        raw_param="",
        metadata={"source_format": suffix.removeprefix(".")},
    )


def _read_csv_rows(path: Path) -> list[tuple[int, list[str | None]]]:
    text = path.read_text(encoding="utf-8-sig")
    first_data_line = next((line for line in text.splitlines() if line.strip()), "")
    delimiter = ";" if ";" in first_data_line else "\t" if "\t" in first_data_line else ","
    return [
        (number, list(row))
        for number, row in enumerate(csv.reader(text.splitlines(), delimiter=delimiter), 1)
    ]


def _read_xlsx_rows(path: Path) -> list[tuple[int, list[str | None]]]:
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise TabularMeasurementFormatError("only .xlsx Excel workbooks are supported")
    with ZipFile(path) as archive:
        shared = _shared_strings(archive)
        sheet_path = _first_sheet_path(archive)
        root = ElementTree.fromstring(archive.read(sheet_path))
    namespace = {"x": _SPREADSHEET_NS}
    result: list[tuple[int, list[str | None]]] = []
    for row in root.findall(".//x:sheetData/x:row", namespace):
        row_number = int(row.attrib.get("r", len(result) + 1))
        values: dict[int, str | None] = {}
        for cell in row.findall("x:c", namespace):
            reference = cell.attrib.get("r", "")
            match = _CELL_REFERENCE.fullmatch(reference)
            if match is None:
                continue
            column = _column_index(match.group(1))
            values[column] = _xlsx_cell_value(cell, shared, namespace)
        width = max(values, default=-1) + 1
        result.append((row_number, [values.get(index) for index in range(width)]))
    return result


def _first_sheet_path(archive: ZipFile) -> str:
    namespace = {"x": _SPREADSHEET_NS, "r": _RELATIONSHIPS_NS}
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    sheet = workbook.find(".//x:sheets/x:sheet", namespace)
    if sheet is None:
        raise TabularMeasurementFormatError("Excel workbook contains no worksheets")
    relationship_id = sheet.attrib.get(f"{{{_RELATIONSHIPS_NS}}}id")
    relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for relationship in relationships:
        if relationship.attrib.get("Id") == relationship_id:
            target = PurePosixPath(relationship.attrib["Target"])
            if target.is_absolute() or ".." in target.parts:
                raise TabularMeasurementFormatError("invalid Excel worksheet path")
            return str(target if target.parts[:1] == ("xl",) else PurePosixPath("xl") / target)
    raise TabularMeasurementFormatError("Excel worksheet relationship is missing")


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    namespace = {"x": _SPREADSHEET_NS}
    return ["".join(node.text or "" for node in item.findall(".//x:t", namespace)) for item in root]


def _xlsx_cell_value(cell, shared: list[str], namespace: dict[str, str]) -> str | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//x:t", namespace))
    value = cell.find("x:v", namespace)
    if value is None or value.text is None:
        return None
    if cell_type == "s":
        try:
            return shared[int(value.text)]
        except (ValueError, IndexError) as exc:
            raise TabularMeasurementFormatError("invalid Excel shared string reference") from exc
    return value.text


def _column_index(letters: str) -> int:
    result = 0
    for letter in letters:
        result = result * 26 + ord(letter) - ord("A") + 1
    return result - 1


def _numeric_row(cells: list[str | None], row_number: int) -> tuple[float, ...] | None:
    while cells and (cells[-1] is None or not str(cells[-1]).strip()):
        cells.pop()
    if not cells:
        return None
    result: list[float] = []
    for column, item in enumerate(cells, 1):
        text = "" if item is None else str(item).strip()
        if not text:
            raise TabularMeasurementFormatError(
                f"row {row_number}, column {column} is empty"
            )
        try:
            number = float(text)
        except ValueError as exc:
            raise TabularMeasurementFormatError(
                f"row {row_number}, column {column} is not numeric"
            ) from exc
        if not math.isfinite(number):
            raise TabularMeasurementFormatError(
                f"row {row_number}, column {column} is not finite"
            )
        result.append(number)
    return tuple(result)


def _positive_frame_rate(value: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TabularMeasurementFormatError("fallback_frame_rate_hz must be positive") from exc
    if not math.isfinite(result) or result <= 0:
        raise TabularMeasurementFormatError("fallback_frame_rate_hz must be positive")
    return result


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise TabularMeasurementFormatError("recording_started_at_utc must be timezone-aware")
    return value.astimezone(timezone.utc)
