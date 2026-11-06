"""Validated application configuration loaded from environment variables."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
from typing import Mapping


class ConfigurationError(ValueError):
    """Raised when configuration cannot be made safe with a fallback."""


class DataMode(str, Enum):
    SIMULATION = "simulation"
    DEVICE = "device"
    FROMFILE = "fromfile"


_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_SIMULATION_SCENARIOS = frozenset({
    "eupnea", "apnea", "tachypnea", "electrode_loss", "noise", "disconnect"
})
_DEFAULT_FROMFILE_PATH = Path(
    "examples/fromfile/test_2.json"
)


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Process configuration with safe demonstration defaults."""

    data_mode: DataMode = DataMode.FROMFILE
    simulation_seed: int = 0
    simulation_scenario: str = "eupnea"
    simulation_speed: float = 1.0
    simulation_respiratory_rate_bpm: float = 12.0
    simulation_duration_seconds: float = 300.0
    fromfile_path: Path = _DEFAULT_FROMFILE_PATH
    fromfile_speed: float = 1.0
    database_path: Path = Path("data/fromfile/eit.sqlite3")
    raw_data_dir: Path = Path("data/fromfile/frames")
    export_dir: Path = Path("exports")
    breath_model_path: Path | None = None
    device_endpoint: str | None = None
    log_level: str = "INFO"
    log_path: Path = Path("data/fromfile/logs/eit.jsonl")
    log_max_bytes: int = 2_000_000
    log_backup_count: int = 5
    diagnostics: tuple[str, ...] = ()

    @property
    def simulated(self) -> bool:
        # File playback is isolated from live-device studies.  The bundled
        # recordings come from calculation/monitoring projects and must not be
        # presented or persisted as measurements acquired from real hardware.
        return self.data_mode in {DataMode.SIMULATION, DataMode.FROMFILE}

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AppConfig":
        values = os.environ if environ is None else environ
        diagnostics: list[str] = []

        raw_mode = values.get("EIT_DATA_MODE", DataMode.FROMFILE.value)
        try:
            data_mode = DataMode(raw_mode.strip().lower())
        except ValueError:
            data_mode = DataMode.SIMULATION
            diagnostics.append(
                f"Unknown EIT_DATA_MODE={raw_mode!r}; using safe simulation mode"
            )

        raw_seed = values.get("EIT_SIMULATION_SEED", "0")
        try:
            simulation_seed = int(raw_seed)
            if simulation_seed < 0:
                raise ValueError
        except ValueError:
            simulation_seed = 0
            diagnostics.append(
                f"Invalid EIT_SIMULATION_SEED={raw_seed!r}; using 0"
            )

        simulation_scenario = values.get("EIT_SIMULATION_SCENARIO", "eupnea").strip().lower()
        if simulation_scenario not in _SIMULATION_SCENARIOS:
            diagnostics.append(
                f"Invalid EIT_SIMULATION_SCENARIO={simulation_scenario!r}; using eupnea"
            )
            simulation_scenario = "eupnea"
        simulation_speed = _positive_float(
            values, "EIT_SIMULATION_SPEED", 1.0, diagnostics
        )
        simulation_respiratory_rate_bpm = _bounded_float(
            values,
            "EIT_SIMULATION_RR_BPM",
            12.0,
            diagnostics,
            minimum=5.0,
            maximum=30.0,
        )
        simulation_duration_seconds = _positive_float(
            values, "EIT_SIMULATION_DURATION_SECONDS", 300.0, diagnostics
        )
        fromfile_path = _path_value(
            values,
            "EIT_FROMFILE_PATH",
            _DEFAULT_FROMFILE_PATH,
            diagnostics,
        )
        fromfile_speed = _positive_float(
            values, "EIT_FROMFILE_SPEED", 1.0, diagnostics
        )
        if data_mode is DataMode.FROMFILE and not fromfile_path.is_file():
            diagnostics.append(
                f"EIT_DATA_MODE=fromfile selected but EIT_FROMFILE_PATH={str(fromfile_path)!r} "
                "is not a readable file"
            )

        mode_dir = data_mode.value
        database_path = _path_value(
            values,
            "EIT_DATABASE_PATH",
            Path("data") / mode_dir / "eit.sqlite3",
            diagnostics,
        )
        raw_data_dir = _path_value(
            values,
            "EIT_RAW_DATA_DIR",
            Path("data") / mode_dir / "frames",
            diagnostics,
        )
        export_dir = _path_value(
            values,
            "EIT_EXPORT_DIR",
            Path("exports"),
            diagnostics,
        )
        raw_breath_model = values.get("EIT_BREATH_MODEL_PATH", "").strip()
        breath_model_path = (
            Path(raw_breath_model).expanduser() if raw_breath_model else None
        )

        endpoint = values.get("EIT_DEVICE_ENDPOINT", "").strip() or None
        if data_mode is DataMode.DEVICE and endpoint is None:
            diagnostics.append(
                "EIT_DATA_MODE=device selected without EIT_DEVICE_ENDPOINT; "
                "hardware source will remain unavailable"
            )

        raw_level = values.get("EIT_LOG_LEVEL", "INFO").strip().upper()
        if raw_level not in _LOG_LEVELS:
            diagnostics.append(
                f"Invalid EIT_LOG_LEVEL={raw_level!r}; using INFO"
            )
            raw_level = "INFO"

        log_path = _path_value(
            values,
            "EIT_LOG_PATH",
            Path("data") / mode_dir / "logs" / "eit.jsonl",
            diagnostics,
        )
        log_max_bytes = _positive_int(
            values,
            "EIT_LOG_MAX_BYTES",
            2_000_000,
            diagnostics,
        )
        log_backup_count = _positive_int(
            values,
            "EIT_LOG_BACKUP_COUNT",
            5,
            diagnostics,
            allow_zero=True,
        )

        return cls(
            data_mode=data_mode,
            simulation_seed=simulation_seed,
            simulation_scenario=simulation_scenario,
            simulation_speed=simulation_speed,
            simulation_respiratory_rate_bpm=simulation_respiratory_rate_bpm,
            simulation_duration_seconds=simulation_duration_seconds,
            fromfile_path=fromfile_path,
            fromfile_speed=fromfile_speed,
            database_path=database_path,
            raw_data_dir=raw_data_dir,
            export_dir=export_dir,
            breath_model_path=breath_model_path,
            device_endpoint=endpoint,
            log_level=raw_level,
            log_path=log_path,
            log_max_bytes=log_max_bytes,
            log_backup_count=log_backup_count,
            diagnostics=tuple(diagnostics),
        )


def _path_value(
    values: Mapping[str, str],
    key: str,
    default: Path,
    diagnostics: list[str],
) -> Path:
    raw = values.get(key)
    if raw is None:
        return default
    if not raw.strip():
        diagnostics.append(f"Empty {key}; using {default}")
        return default
    return Path(raw.strip()).expanduser()


def _positive_int(
    values: Mapping[str, str],
    key: str,
    default: int,
    diagnostics: list[str],
    *,
    allow_zero: bool = False,
) -> int:
    raw = values.get(key)
    if raw is None:
        return default
    try:
        parsed = int(raw)
        if parsed < 0 or (parsed == 0 and not allow_zero):
            raise ValueError
        return parsed
    except ValueError:
        diagnostics.append(f"Invalid {key}={raw!r}; using {default}")
        return default


def _positive_float(
    values: Mapping[str, str],
    key: str,
    default: float,
    diagnostics: list[str],
) -> float:
    raw = values.get(key)
    if raw is None:
        return default
    try:
        parsed = float(raw)
        if parsed <= 0 or parsed == float("inf") or parsed != parsed:
            raise ValueError
        return parsed
    except ValueError:
        diagnostics.append(f"Invalid {key}={raw!r}; using {default}")
        return default


def _bounded_float(
    values: Mapping[str, str],
    key: str,
    default: float,
    diagnostics: list[str],
    *,
    minimum: float,
    maximum: float,
) -> float:
    raw = values.get(key)
    if raw is None:
        return default
    try:
        parsed = float(raw)
        if not minimum <= parsed <= maximum or parsed != parsed:
            raise ValueError
        return parsed
    except ValueError:
        diagnostics.append(
            f"Invalid {key}={raw!r}; using {default} "
            f"(allowed range {minimum:g}..{maximum:g})"
        )
        return default
