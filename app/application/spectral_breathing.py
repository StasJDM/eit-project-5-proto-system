"""Experimental spectral-temporal breathing-pattern classifier.

The implementation intentionally avoids PCA and trained models.  It combines a
Welch spectrum with a time-domain RMS envelope so that rate and regularity come
from the spectrum while pauses remain localized in time.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from .breathing_classification import BreathingClass, BreathingClassificationResult


SPECTRAL_ALGORITHM_VERSION = "spectral-temporal-welch-1.1.0"
MIN_WINDOW_SECONDS = 30.0
MAX_WINDOW_SECONDS = 60.0
MIN_RESPIRATORY_RATE_BPM = 5.0
MAX_RESPIRATORY_RATE_BPM = 60.0
DEFAULT_BRADYPNEA_LIMIT_BPM = 10.0
DEFAULT_TACHYPNEA_LIMIT_BPM = 30.0
APNEA_PAUSE_SECONDS = 10.0


class SpectralBreathingClassifier:
    """Classify observable breathing patterns from one global EIT curve."""

    clinically_validated = False
    operational = True
    algorithm_version = SPECTRAL_ALGORITHM_VERSION

    def __init__(
        self,
        *,
        bradypnea_limit_bpm: float = DEFAULT_BRADYPNEA_LIMIT_BPM,
        tachypnea_limit_bpm: float = DEFAULT_TACHYPNEA_LIMIT_BPM,
    ) -> None:
        if not 0 < bradypnea_limit_bpm < tachypnea_limit_bpm:
            raise ValueError("breathing-rate limits are invalid")
        self._bradypnea_limit_bpm = float(bradypnea_limit_bpm)
        self._tachypnea_limit_bpm = float(tachypnea_limit_bpm)

    def classify(
        self,
        values: np.ndarray,
        sample_rate_hz: float,
        interval_start_utc: datetime,
        interval_end_utc: datetime,
    ) -> BreathingClassificationResult:
        signal = np.asarray(values, dtype=float).reshape(-1)
        if (
            not np.isfinite(sample_rate_hz)
            or sample_rate_hz <= 0
            or signal.size < round(MIN_WINDOW_SECONDS * sample_rate_hz)
            or not np.all(np.isfinite(signal))
        ):
            return self._undetermined(
                interval_start_utc, interval_end_utc,
                "spectral_insufficient_signal",
            )

        max_samples = max(2, round(MAX_WINDOW_SECONDS * sample_rate_hz))
        signal = signal[-max_samples:]
        analysis_start = max(
            interval_start_utc,
            interval_end_utc - timedelta(
                seconds=(signal.size - 1) / sample_rate_hz
            ),
        )
        centered = _linear_detrend(signal)
        robust_range = float(np.quantile(centered, 0.95) - np.quantile(centered, 0.05))
        numerical_floor = np.finfo(float).eps * max(1.0, float(np.max(np.abs(signal))))
        if robust_range <= numerical_floor:
            return self._undetermined(
                analysis_start, interval_end_utc, "spectral_low_energy"
            )

        envelope = _rms_envelope(centered, sample_rate_hz)
        reference = float(np.quantile(envelope, 0.75))
        if reference <= numerical_floor:
            return self._undetermined(
                analysis_start, interval_end_utc, "spectral_low_energy"
            )
        silent = envelope < 0.15 * reference
        edge = min(silent.size // 4, max(1, round(0.75 * sample_rate_hz)))
        silent[:edge] = False
        silent[-edge:] = False
        longest_pause = _longest_true_run(silent) / sample_rate_hz

        frequencies, power = _welch_spectrum(centered, sample_rate_hz)
        respiratory_band = (
            (frequencies >= MIN_RESPIRATORY_RATE_BPM / 60.0)
            & (frequencies <= MAX_RESPIRATORY_RATE_BPM / 60.0)
        )
        wider_band = (frequencies >= 0.02) & (
            frequencies <= min(2.0, sample_rate_hz / 2.0)
        )
        respiratory_power = float(np.sum(power[respiratory_band]))
        wider_power = float(np.sum(power[wider_band]))
        if respiratory_power <= numerical_floor or wider_power <= numerical_floor:
            return self._undetermined(
                analysis_start, interval_end_utc, "spectral_low_energy"
            )

        band_indices = np.flatnonzero(respiratory_band)
        peak_index = int(band_indices[np.argmax(power[respiratory_band])])
        peak_frequency = float(frequencies[peak_index])
        respiratory_rate = peak_frequency * 60.0
        bin_width = float(frequencies[1] - frequencies[0])
        peak_half_width = max(0.04, 2.0 * bin_width)
        peak_band = np.abs(frequencies - peak_frequency) <= peak_half_width
        concentration = float(np.sum(power[peak_band]) / respiratory_power)
        spectral_quality = float(np.clip(respiratory_power / wider_power, 0.0, 1.0))
        modulation_score, envelope_cv = _envelope_modulation(envelope, sample_rate_hz)
        gasping_score = _gasping_score(centered, envelope, sample_rate_hz)

        if gasping_score > 0.0:
            return self._result(
                BreathingClass.GASPING,
                min(0.92, 0.55 + 0.37 * gasping_score),
                analysis_start,
                interval_end_utc,
            )
        if longest_pause >= APNEA_PAUSE_SECONDS:
            return self._result(
                BreathingClass.APNEA,
                min(0.99, 0.65 + 0.35 * longest_pause / 20.0),
                analysis_start,
                interval_end_utc,
            )
        if modulation_score >= 0.45 and envelope_cv >= 0.30:
            return self._result(
                BreathingClass.PERIODIC,
                min(0.95, 0.45 + 0.35 * modulation_score + 0.20 * envelope_cv),
                analysis_start,
                interval_end_utc,
            )
        if spectral_quality >= 0.65 and concentration < 0.45:
            irregularity = float(np.clip((0.45 - concentration) / 0.30, 0.0, 1.0))
            return self._result(
                BreathingClass.DYSPNEA,
                min(0.85, 0.50 + 0.25 * irregularity + 0.10 * envelope_cv),
                analysis_start,
                interval_end_utc,
            )
        if spectral_quality < 0.45 or concentration < 0.35:
            return self._undetermined(
                analysis_start, interval_end_utc, "spectral_irregular_pattern"
            )
        if respiratory_rate > self._tachypnea_limit_bpm:
            margin = (respiratory_rate - self._tachypnea_limit_bpm) / 15.0
            breathing_class = BreathingClass.TACHYPNEA
        elif respiratory_rate < self._bradypnea_limit_bpm:
            margin = (self._bradypnea_limit_bpm - respiratory_rate) / 5.0
            breathing_class = BreathingClass.BRADYPNEA
        else:
            margin = min(
                respiratory_rate - self._bradypnea_limit_bpm,
                self._tachypnea_limit_bpm - respiratory_rate,
            ) / 10.0
            breathing_class = BreathingClass.EUPNEA
        confidence = float(np.clip(
            0.35 + 0.35 * concentration + 0.20 * spectral_quality + 0.10 * margin,
            0.0,
            0.95,
        ))
        return self._result(
            breathing_class, confidence, analysis_start, interval_end_utc
        )

    def _result(
        self,
        breathing_class: BreathingClass,
        confidence: float,
        start: datetime,
        end: datetime,
    ) -> BreathingClassificationResult:
        return BreathingClassificationResult(
            breathing_class,
            float(np.clip(confidence, 0.0, 1.0)),
            start,
            end,
            self.algorithm_version,
            "experimental_spectral_classifier",
        )

    def _undetermined(
        self, start: datetime, end: datetime, reason: str
    ) -> BreathingClassificationResult:
        return BreathingClassificationResult(
            BreathingClass.UNDETERMINED,
            0.0,
            start,
            end,
            self.algorithm_version,
            reason,
        )


def _linear_detrend(values: np.ndarray) -> np.ndarray:
    x = np.linspace(-1.0, 1.0, values.size)
    slope, intercept = np.polyfit(x, values, 1)
    return values - (slope * x + intercept)


def _rms_envelope(values: np.ndarray, sample_rate_hz: float) -> np.ndarray:
    window = max(3, round(1.5 * sample_rate_hz))
    kernel = np.full(window, 1.0 / window)
    return np.sqrt(np.maximum(0.0, np.convolve(values * values, kernel, mode="same")))


def _welch_spectrum(
    values: np.ndarray, sample_rate_hz: float
) -> tuple[np.ndarray, np.ndarray]:
    segment_size = min(values.size, max(8, round(MAX_WINDOW_SECONDS * sample_rate_hz)))
    step = max(1, segment_size // 2)
    starts = list(range(0, values.size - segment_size + 1, step)) or [0]
    window = np.hanning(segment_size)
    scale = max(float(np.sum(window * window)), np.finfo(float).tiny)
    spectra = []
    for start in starts:
        segment = _linear_detrend(values[start:start + segment_size])
        transformed = np.fft.rfft(segment * window)
        spectra.append((np.abs(transformed) ** 2) / scale)
    power = np.mean(spectra, axis=0)
    return np.fft.rfftfreq(segment_size, d=1.0 / sample_rate_hz), power


def _envelope_modulation(
    envelope: np.ndarray, sample_rate_hz: float
) -> tuple[float, float]:
    stride = max(1, round(sample_rate_hz))
    sampled = envelope[::stride]
    mean = float(np.mean(sampled))
    if sampled.size < 20 or mean <= np.finfo(float).tiny:
        return 0.0, 0.0
    centered = _linear_detrend(sampled)
    frequencies = np.fft.rfftfreq(sampled.size, d=stride / sample_rate_hz)
    power = np.abs(np.fft.rfft(centered * np.hanning(sampled.size))) ** 2
    modulation_band = (frequencies >= 0.015) & (frequencies <= 0.08)
    comparison_band = (frequencies > 0.0) & (frequencies <= 0.25)
    denominator = float(np.sum(power[comparison_band]))
    score = float(np.sum(power[modulation_band]) / denominator) if denominator > 0 else 0.0
    return score, float(np.std(sampled) / mean)


def _longest_true_run(values: np.ndarray) -> int:
    longest = current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def _gasping_score(
    values: np.ndarray, envelope: np.ndarray, sample_rate_hz: float
) -> float:
    """Return a heuristic score for sparse, high-crest-factor breath bursts."""
    maximum = float(np.max(envelope))
    rms = float(np.sqrt(np.mean(values * values)))
    if maximum <= np.finfo(float).tiny or rms <= np.finfo(float).tiny:
        return 0.0
    active = envelope >= 0.30 * maximum
    minimum_burst = max(1, round(0.35 * sample_rate_hz))
    burst_lengths = _true_run_lengths(active)
    bursts = [length for length in burst_lengths if length >= minimum_burst]
    inactive_fraction = 1.0 - float(np.mean(active))
    longest_gap = _longest_true_run(~active) / sample_rate_hz
    crest_factor = float(np.max(np.abs(values)) / rms)
    median_burst = (
        float(np.median(bursts)) / sample_rate_hz if bursts else float("inf")
    )
    if not (
        2 <= len(bursts) <= 12
        and inactive_fraction >= 0.45
        and longest_gap >= 1.5
        and median_burst <= 3.0
        and crest_factor >= 2.8
    ):
        return 0.0
    return float(np.clip(
        0.35 * inactive_fraction
        + 0.25 * min(longest_gap / 6.0, 1.0)
        + 0.40 * min((crest_factor - 2.0) / 3.0, 1.0),
        0.0,
        1.0,
    ))


def _true_run_lengths(values: np.ndarray) -> list[int]:
    lengths: list[int] = []
    current = 0
    for value in values:
        if value:
            current += 1
        elif current:
            lengths.append(current)
            current = 0
    if current:
        lengths.append(current)
    return lengths
