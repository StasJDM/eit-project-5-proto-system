"""Compressed immutable NumPy chunks for high-volume EIT frames."""

from __future__ import annotations

from pathlib import Path
import logging
import os
import tempfile
from uuid import UUID

import numpy as np

from ..domain import DataQuality, EITFrame
from .database import DatabaseModeError
from ..technical_logging import get_logger, technical_event


_logger = get_logger("frame_store")


class NpzFrameStore:
    def __init__(self, root: Path | str, *, simulated: bool) -> None:
        self.root = Path(root)
        self.simulated = simulated
        self.root.mkdir(parents=True, exist_ok=True)

    def append_chunk(
        self,
        study_id: UUID,
        session_id: UUID,
        frames: tuple[EITFrame, ...] | list[EITFrame],
    ) -> Path:
        if not frames:
            raise ValueError("frames must not be empty")
        if any(frame.simulated != self.simulated for frame in frames):
            raise DatabaseModeError("frame mode does not match frame-store mode")
        sequences = [frame.sequence_number for frame in frames]
        if sequences != sorted(sequences) or len(set(sequences)) != len(sequences):
            raise ValueError("frame sequence numbers must be strictly increasing")
        roi_shape = len(frames[0].roi_impedance)
        map_shape = np.asarray(frames[0].reconstructed_delta_z).shape
        if any(
            len(frame.roi_impedance) != roi_shape
            or np.asarray(frame.reconstructed_delta_z).shape != map_shape
            or (
                frame.absolute_conductivity is not None
                and np.asarray(frame.absolute_conductivity).shape != map_shape
            )
            for frame in frames
        ):
            raise ValueError("all frames in a chunk must have identical shapes")

        directory = self.root / str(study_id) / str(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{sequences[0]:012d}-{sequences[-1]:012d}.npz"
        if target.exists():
            raise FileExistsError(f"frame chunk already exists: {target}")

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".chunk-", suffix=".npz", dir=directory
        )
        try:
            with os.fdopen(descriptor, "wb") as output:
                np.savez_compressed(
                    output,
                    sequence_number=np.asarray(sequences, dtype=np.int64),
                    timestamp_utc=np.asarray(
                        [frame.timestamp_utc.isoformat() for frame in frames], dtype="U40"
                    ),
                    belt_index=np.asarray([frame.belt_index for frame in frames], dtype=np.int16),
                    global_impedance=np.asarray(
                        [frame.global_impedance for frame in frames], dtype=np.float64
                    ),
                    roi_impedance=np.asarray(
                        [frame.roi_impedance for frame in frames], dtype=np.float64
                    ),
                    reconstructed_delta_z=np.asarray(
                        [frame.reconstructed_delta_z for frame in frames], dtype=np.float32
                    ),
                    has_absolute_conductivity=np.asarray(
                        [frame.absolute_conductivity is not None for frame in frames],
                        dtype=np.bool_,
                    ),
                    absolute_conductivity=np.asarray(
                        [
                            frame.absolute_conductivity
                            if frame.absolute_conductivity is not None
                            else np.zeros(map_shape, dtype=float)
                            for frame in frames
                        ],
                        dtype=np.float32,
                    ),
                    quality=np.asarray([frame.quality.value for frame in frames], dtype="U16"),
                    simulated=np.asarray([frame.simulated for frame in frames], dtype=np.bool_),
                    format_version=np.asarray(
                        [frame.format_version for frame in frames], dtype=np.int16
                    ),
                )
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_name, target)
        except Exception:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
            raise
        technical_event(
            _logger,
            logging.INFO,
            "frame_chunk.written",
            study_id=study_id,
            session_id=session_id,
            frame_count=len(frames),
            simulated=self.simulated,
            result="success",
        )
        return target

    def load(self, study_id: UUID, session_id: UUID) -> tuple[EITFrame, ...]:
        directory = self.root / str(study_id) / str(session_id)
        if not directory.exists():
            return ()
        frames: list[EITFrame] = []
        for path in sorted(directory.glob("*.npz")):
            with np.load(path, allow_pickle=False) as chunk:
                for index in range(len(chunk["sequence_number"])):
                    from datetime import datetime

                    frames.append(
                        EITFrame(
                            sequence_number=int(chunk["sequence_number"][index]),
                            timestamp_utc=datetime.fromisoformat(
                                str(chunk["timestamp_utc"][index])
                            ),
                            belt_index=int(chunk["belt_index"][index]),
                            global_impedance=float(chunk["global_impedance"][index]),
                            roi_impedance=tuple(
                                float(value) for value in chunk["roi_impedance"][index]
                            ),
                            reconstructed_delta_z=tuple(
                                tuple(float(value) for value in row)
                                for row in chunk["reconstructed_delta_z"][index]
                            ),
                            absolute_conductivity=(
                                tuple(
                                    tuple(float(value) for value in row)
                                    for row in chunk["absolute_conductivity"][index]
                                )
                                if "absolute_conductivity" in chunk.files
                                and bool(chunk["has_absolute_conductivity"][index])
                                else None
                            ),
                            quality=DataQuality(str(chunk["quality"][index])),
                            simulated=bool(chunk["simulated"][index]),
                            format_version=int(chunk["format_version"][index]),
                        )
                    )
        return tuple(frames)
