"""Crash-safe chunked recording of frames received by the acquisition pipeline."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from threading import RLock
from typing import Any, TypeAlias
from uuid import UUID

import numpy as np

from ..data_sources.base import TimestampSource
from ..data_sources.json_contract import RawMeasurementFrame
from ..domain import DataQuality, EITFrame


RECORDING_SCHEMA_VERSION = 1
SourceFrame: TypeAlias = EITFrame | RawMeasurementFrame


@dataclass(frozen=True, slots=True)
class RecordingMetadata:
    study_id: UUID
    session_id: UUID
    status: str
    simulated: bool
    frame_rate_hz: float
    frame_kind: str | None
    frame_count: int


class RecordingError(RuntimeError):
    pass


class InsufficientDiskSpaceError(RecordingError):
    pass


@dataclass(frozen=True, slots=True)
class RecordingChunk:
    path: Path
    checksum: str
    kind: str

    def read(self) -> list[SourceFrame]:
        if _sha256(self.path) != self.checksum:
            raise RecordingError(f"checksum mismatch: {self.path.name}")
        return _load_chunk(self.path, self.kind)


class AcquisitionRecordingStore:
    def __init__(
        self,
        root: Path | str,
        *,
        simulated: bool,
        chunk_size: int = 64,
        minimum_free_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if minimum_free_bytes < 0:
            raise ValueError("minimum_free_bytes must be non-negative")
        self.root = Path(root)
        self.simulated = simulated
        self.chunk_size = chunk_size
        self.minimum_free_bytes = minimum_free_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def open_writer(
        self,
        study_id: UUID,
        session_id: UUID,
        *,
        frame_rate_hz: float,
    ) -> "AcquisitionRecordingWriter":
        return AcquisitionRecordingWriter(
            self, study_id, session_id, frame_rate_hz=frame_rate_hz
        )

    def load(self, study_id: UUID, session_id: UUID) -> tuple[SourceFrame, ...]:
        return tuple(frame for _, frames in self.iter_chunks(study_id, session_id)
                     for frame in frames)

    def iter_chunks(
        self, study_id: UUID, session_id: UUID
    ) -> Iterator[tuple[RecordingChunk, list[SourceFrame]]]:
        directory = self.root / str(study_id) / str(session_id)
        manifest = _read_manifest(directory / "manifest.json")
        previous = None
        count = 0
        for entry in manifest.get("chunks", []):
            chunk = RecordingChunk(directory / entry["file"], entry["sha256"], manifest["frame_kind"])
            frames = chunk.read()
            for frame in frames:
                if previous is not None and frame.sequence_number <= previous:
                    raise RecordingError("recording contains duplicate or reversed sequences")
                previous = frame.sequence_number
            count += len(frames)
            yield chunk, frames
        if count != manifest.get("frame_count"):
            raise RecordingError("recording frame count does not match manifest")

    def metadata(self, study_id: UUID, session_id: UUID) -> RecordingMetadata:
        """Return validated, immutable playback metadata without exposing the manifest."""
        manifest = _read_manifest(
            self.root / str(study_id) / str(session_id) / "manifest.json"
        )
        try:
            if manifest.get("study_id") != str(study_id):
                raise RecordingError("recording study id does not match its directory")
            if manifest.get("session_id") != str(session_id):
                raise RecordingError("recording session id does not match its directory")
            frame_rate_hz = float(manifest["frame_rate_hz"])
            frame_count = int(manifest["frame_count"])
            if frame_rate_hz <= 0 or frame_count < 0:
                raise ValueError
            return RecordingMetadata(
                study_id=study_id,
                session_id=session_id,
                status=str(manifest["status"]),
                simulated=bool(manifest["simulated"]),
                frame_rate_hz=frame_rate_hz,
                frame_kind=manifest.get("frame_kind"),
                frame_count=frame_count,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RecordingError("invalid recording playback metadata") from exc

    def recover_incomplete(self) -> tuple[Path, ...]:
        recovered: list[Path] = []
        for manifest_path in self.root.glob("*/*/manifest.json"):
            manifest = _read_manifest(manifest_path)
            if manifest.get("status") != "recording":
                continue
            directory = manifest_path.parent
            entries = []
            for path in sorted(directory.glob("*.npz")):
                if path.name.startswith("."):
                    continue
                with np.load(path, allow_pickle=False) as chunk:
                    sequences = chunk["sequence_number"]
                    if len(sequences) == 0:
                        continue
                    entries.append({
                        "file": path.name,
                        "first_sequence": int(sequences[0]),
                        "last_sequence": int(sequences[-1]),
                        "frame_count": int(len(sequences)),
                        "sha256": _sha256(path),
                    })
            manifest["chunks"] = entries
            manifest["frame_count"] = sum(item["frame_count"] for item in entries)
            manifest["status"] = "interrupted"
            manifest["updated_at_utc"] = _now_text()
            _write_manifest(manifest_path, manifest)
            recovered.append(manifest_path)
        return tuple(recovered)


class AcquisitionRecordingWriter:
    def __init__(
        self,
        store: AcquisitionRecordingStore,
        study_id: UUID,
        session_id: UUID,
        *,
        frame_rate_hz: float,
    ) -> None:
        if frame_rate_hz <= 0:
            raise ValueError("frame_rate_hz must be positive")
        self._store = store
        self.study_id = study_id
        self.session_id = session_id
        self._directory = store.root / str(study_id) / str(session_id)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._manifest_path = self._directory / "manifest.json"
        if self._manifest_path.exists():
            raise FileExistsError(f"recording already exists: {self._manifest_path}")
        self._buffer: list[SourceFrame] = []
        self._last_sequence: int | None = None
        self._closed = False
        self._lock = RLock()
        self._manifest: dict[str, Any] = {
            "schema_version": RECORDING_SCHEMA_VERSION,
            "study_id": str(study_id),
            "session_id": str(session_id),
            "status": "recording",
            "simulated": store.simulated,
            "frame_rate_hz": float(frame_rate_hz),
            "frame_kind": None,
            "protocol_id": None,
            "channel_count": None,
            "frame_count": 0,
            "chunks": [],
            "started_at_utc": _now_text(),
            "updated_at_utc": _now_text(),
            "completed_at_utc": None,
        }
        _write_manifest(self._manifest_path, self._manifest)

    def append(self, frame: SourceFrame) -> None:
        with self._lock:
            self._ensure_open()
            if frame.simulated != self._store.simulated:
                raise RecordingError("frame mode does not match recording store")
            if self._last_sequence is not None and frame.sequence_number <= self._last_sequence:
                raise RecordingError("frame sequence must be strictly increasing")
            kind = "raw_measurement" if isinstance(frame, RawMeasurementFrame) else "eit_frame"
            if self._manifest["frame_kind"] is None:
                self._manifest["frame_kind"] = kind
                if isinstance(frame, RawMeasurementFrame):
                    self._manifest["protocol_id"] = frame.protocol_id
                    self._manifest["channel_count"] = len(frame.channel_values)
                _write_manifest(self._manifest_path, self._manifest)
            elif self._manifest["frame_kind"] != kind:
                raise RecordingError("frame kind changed inside one recording")
            self._buffer.append(frame)
            self._last_sequence = frame.sequence_number
            if len(self._buffer) >= self._store.chunk_size:
                self.flush()

    def flush(self) -> None:
        with self._lock:
            self._ensure_open()
            if not self._buffer:
                return
            frames = tuple(self._buffer)
            estimated_size = _estimated_bytes(frames)
            free = shutil.disk_usage(self._directory).free
            if free - estimated_size < self._store.minimum_free_bytes:
                raise InsufficientDiskSpaceError(
                    f"not enough free space for recording chunk: free={free}, "
                    f"required_reserve={self._store.minimum_free_bytes}"
                )
            first = frames[0].sequence_number
            last = frames[-1].sequence_number
            target = self._directory / f"{first:012d}-{last:012d}.npz"
            if target.exists():
                raise FileExistsError(f"recording chunk already exists: {target}")
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".chunk-", suffix=".npz", dir=self._directory
            )
            try:
                with os.fdopen(descriptor, "wb") as output:
                    _write_chunk(output, frames)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary_name, target)
            except Exception:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
                raise
            entry = {
                "file": target.name,
                "first_sequence": first,
                "last_sequence": last,
                "frame_count": len(frames),
                "sha256": _sha256(target),
            }
            self._manifest["chunks"].append(entry)
            self._manifest["frame_count"] += len(frames)
            self._manifest["updated_at_utc"] = _now_text()
            _write_manifest(self._manifest_path, self._manifest)
            self._buffer.clear()

    def close(self, *, completed: bool = True) -> None:
        with self._lock:
            if self._closed:
                return
            self.flush()
            self._manifest["status"] = "completed" if completed else "interrupted"
            self._manifest["updated_at_utc"] = _now_text()
            self._manifest["completed_at_utc"] = _now_text() if completed else None
            _write_manifest(self._manifest_path, self._manifest)
            self._closed = True

    @property
    def manifest(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._manifest))

    def _ensure_open(self) -> None:
        if self._closed:
            raise RecordingError("recording writer is closed")


def _write_chunk(output, frames: tuple[SourceFrame, ...]) -> None:
    common = {
        "sequence_number": np.asarray([item.sequence_number for item in frames], dtype=np.int64),
        "timestamp_utc": np.asarray([item.timestamp_utc.isoformat() for item in frames], dtype="U40"),
        "belt_index": np.asarray([item.belt_index for item in frames], dtype=np.int16),
        "quality": np.asarray([item.quality.value for item in frames], dtype="U16"),
        "simulated": np.asarray([item.simulated for item in frames], dtype=np.bool_),
    }
    first = frames[0]
    if isinstance(first, RawMeasurementFrame):
        raw_frames = tuple(item for item in frames if isinstance(item, RawMeasurementFrame))
        np.savez_compressed(
            output,
            **common,
            channel_values=np.asarray([item.channel_values for item in raw_frames], dtype=np.float64),
            protocol_id=np.asarray([item.protocol_id for item in raw_frames], dtype="U80"),
            timestamp_source=np.asarray([item.timestamp_source.value for item in raw_frames], dtype="U24"),
        )
    else:
        eit_frames = tuple(item for item in frames if isinstance(item, EITFrame))
        np.savez_compressed(
            output,
            **common,
            global_impedance=np.asarray([item.global_impedance for item in eit_frames], dtype=np.float64),
            roi_impedance=np.asarray([item.roi_impedance for item in eit_frames], dtype=np.float64),
            reconstructed_delta_z=np.asarray([item.reconstructed_delta_z for item in eit_frames], dtype=np.float64),
            has_absolute_conductivity=np.asarray(
                [item.absolute_conductivity is not None for item in eit_frames],
                dtype=np.bool_,
            ),
            absolute_conductivity=np.asarray(
                [
                    item.absolute_conductivity
                    if item.absolute_conductivity is not None
                    else np.zeros_like(item.reconstructed_delta_z, dtype=float)
                    for item in eit_frames
                ],
                dtype=np.float64,
            ),
            format_version=np.asarray([item.format_version for item in eit_frames], dtype=np.int16),
        )


def _load_chunk(path: Path, kind: str) -> list[SourceFrame]:
    result: list[SourceFrame] = []
    with np.load(path, allow_pickle=False) as chunk:
        names = ["sequence_number", "timestamp_utc", "belt_index", "quality", "simulated"]
        if kind == "raw_measurement":
            names += ["channel_values", "protocol_id", "timestamp_source"]
        elif kind == "eit_frame":
            names += ["global_impedance", "roi_impedance", "reconstructed_delta_z", "format_version"]
        else:
            raise RecordingError(f"unknown frame kind: {kind!r}")
        fields = {name: chunk[name] for name in names}
        if kind == "eit_frame" and "absolute_conductivity" in chunk.files:
            flags = fields["has_absolute_conductivity"] = chunk["has_absolute_conductivity"]
            if flags.any():
                fields["absolute_conductivity"] = chunk["absolute_conductivity"]
    for index in range(len(fields["sequence_number"])):
        common = {
            "sequence_number": int(fields["sequence_number"][index]),
            "timestamp_utc": datetime.fromisoformat(str(fields["timestamp_utc"][index])),
            "belt_index": int(fields["belt_index"][index]),
            "quality": DataQuality(str(fields["quality"][index])),
            "simulated": bool(fields["simulated"][index]),
        }
        if kind == "raw_measurement":
            result.append(RawMeasurementFrame(
                **common,
                channel_values=tuple(float(value) for value in fields["channel_values"][index]),
                protocol_id=str(fields["protocol_id"][index]),
                timestamp_source=TimestampSource(str(fields["timestamp_source"][index])),
            ))
        else:
            result.append(EITFrame(
                **common,
                global_impedance=float(fields["global_impedance"][index]),
                roi_impedance=tuple(float(value) for value in fields["roi_impedance"][index]),
                reconstructed_delta_z=tuple(
                    tuple(float(value) for value in row)
                    for row in fields["reconstructed_delta_z"][index]
                ),
                absolute_conductivity=(
                    tuple(
                        tuple(float(value) for value in row)
                        for row in fields["absolute_conductivity"][index]
                    )
                    if "absolute_conductivity" in fields
                    and bool(fields["has_absolute_conductivity"][index])
                    else None
                ),
                format_version=int(fields["format_version"][index]),
            ))
    return result


def _estimated_bytes(frames: tuple[SourceFrame, ...]) -> int:
    first = frames[0]
    if isinstance(first, RawMeasurementFrame):
        values = len(first.channel_values)
    else:
        values = 1 + len(first.roi_impedance) + sum(
            len(row) for row in first.reconstructed_delta_z
        )
    return max(4096, len(frames) * values * 8 * 2)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecordingError(f"cannot read recording manifest: {path}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != RECORDING_SCHEMA_VERSION:
        raise RecordingError("unsupported recording manifest")
    return value


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".manifest-", suffix=".json", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(manifest, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
    except Exception:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
        raise


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat()
