"""Source-independent signal shapes used by demo-only analysis panels."""

from __future__ import annotations

import numpy as np


_INSPIRATION_FRACTION = 0.40
_BASELINE = 0.02


def breath_phase_value(phase: float) -> float:
    phase = phase % 1.0
    if phase < _INSPIRATION_FRACTION:
        value = phase / _INSPIRATION_FRACTION
        if value < 0.25:
            return 0.12 * (value / 0.25) ** 1.6
        if value < 0.78:
            ramp = (value - 0.25) / 0.53
            return 0.12 + 0.82 * (ramp ** 0.62)
        plateau = (value - 0.78) / 0.22
        return 0.94 + 0.06 * (1.0 - (1.0 - plateau) ** 2.0)
    expiration = (phase - _INSPIRATION_FRACTION) / (1.0 - _INSPIRATION_FRACTION)
    return (1.0 - expiration) ** 1.42


def breath_waveform(
    time_seconds: float,
    frequency_hz: float,
    amplitude: float = 1.0,
    phase_radians: float = 0.0,
) -> float:
    phase = (time_seconds * frequency_hz + phase_radians / (2 * np.pi)) % 1.0
    return amplitude * (_BASELINE + (1.0 - _BASELINE) * breath_phase_value(phase))
