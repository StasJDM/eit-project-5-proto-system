"""Mock breathing data generator.

Simulates eupnea (normal breathing) at 15 bpm with 8 regional ROIs.
No real EIT computation — piecewise plethysmogram shaped like real EIT LI.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List

# ── Constants ───────────────────────────────────────────────────────────────
FS = 25          # sample rate, Hz
RR_BPM = 15      # breathing rate, breaths/min
DISPLAY_WINDOW_SEC = 60   # default graph time window (~12–15 breaths at eupnea)
BREATHS_IN_WINDOW = 12    # breath-index bar charts in the same window
DISPLAY_SAMPLES = int(FS * DISPLAY_WINDOW_SEC)
BUFFER_SEC = 90    # rolling buffer length, seconds (must exceed display window)

# Inspiration occupies ~40 % of the cycle (faster insp, slower exp — eupnea).
_INSP_FRAC = 0.40
_EELI_FLOOR = 0.02   # end-expiratory LI offset (normalized)

# ROI amplitude distribution (right lung slightly dominant)
_ROI_AMP = [0.27, 0.24, 0.23, 0.21,   # ROI 1-4  (right)
             0.25, 0.22, 0.20, 0.19]   # ROI 5-8  (left)
# Small phase lags to simulate regional timing differences (radians)
_ROI_PHASE = [0.00, 0.04, 0.02, 0.07,
              0.03, 0.06, 0.01, 0.05]
# Waveform variability: ~5 % RMS multiplicative noise, clipped to ±10 %.
_WAVE_NOISE_STD = 0.05
_WAVE_NOISE_MAX = 0.10


def breath_phase_value(phi: float) -> float:
    """Map breath phase φ∈[0,1) to normalized LI amplitude ∈[0,1].

    Asymmetric eupnea-like profile: slow early inspiration, rapid ramp,
    inspiratory plateau, then gradual passive expiration.
    Tuned against eupnea.json plethysmogram from eit_project_4_monitoring.
    """
    phi = phi % 1.0
    if phi < _INSP_FRAC:
        u = phi / _INSP_FRAC
        if u < 0.25:
            return 0.12 * (u / 0.25) ** 1.6
        if u < 0.78:
            v = (u - 0.25) / 0.53
            return 0.12 + 0.82 * (v ** 0.62)
        w = (u - 0.78) / 0.22
        return 0.94 + 0.06 * (1.0 - (1.0 - w) ** 2.0)
    u = (phi - _INSP_FRAC) / (1.0 - _INSP_FRAC)
    return (1.0 - u) ** 1.42


def breath_waveform(t: float, freq: float, amp: float = 1.0,
                    phase_rad: float = 0.0) -> float:
    """LI-like trace sample at time *t* (seconds)."""
    phi = (t * freq + phase_rad / (2 * np.pi)) % 1.0
    return amp * (_EELI_FLOOR + (1.0 - _EELI_FLOOR) * breath_phase_value(phi))


@dataclass
class BreathingSnapshot:
    """One moment of computed numerical parameters."""
    rr:        float = 15.0   # breathing rate, bpm
    t_pct:     float = 100.0  # global (always 100 %)
    r_pct:     float = 52.0   # right lung share, %
    l_pct:     float = 48.0   # left lung share, %
    lr_ratio:  float = 1.08   # L/R ratio
    vd_ratio:  float = 0.85   # ventral/dorsal ratio
    eeli:      float = 0.45   # end-expiratory LI
    eili:      float = 1.45   # end-inspiratory LI
    tvi:       float = 1.00   # tidal volume index
    phase:     float = 0.0    # current breath phase 0..1 (0=exhale,1=inhale)
    roi_pct:   List[float] = field(default_factory=lambda: [0.0] * 8)
    trend_global: float = 0.0
    trend_r:      float = 0.0
    trend_l:      float = 0.0
    roi_trends:   List[float] = field(default_factory=lambda: [0.0] * 8)


class BreathingSimulator:
    """Generates realistic mock EIT breathing data (no actual physics)."""

    def __init__(self, fs: int = FS, rr: float = RR_BPM, buf_sec: int = BUFFER_SEC):
        self.fs = fs
        self.rr = rr
        self._freq = rr / 60.0            # Hz
        self._buf = int(buf_sec * fs)
        self._dt = 1.0 / fs

        self._t = 0.0                     # current simulation time, s
        self._idx = 0                     # write pointer in ring buffer

        self._time_buf    = np.zeros(self._buf)
        self._global_buf  = np.zeros(self._buf)
        self._roi_bufs    = [np.zeros(self._buf) for _ in range(8)]

        self._prefill()

    # ── Public API ──────────────────────────────────────────────────────────

    def step(self):
        """Advance one sample. Call at `self.fs` Hz."""
        self._t += self._dt
        i = self._idx % self._buf

        self._time_buf[i]   = self._t
        self._global_buf[i] = self._global(self._t)
        for j in range(8):
            self._roi_bufs[j][i] = self._roi(self._t, j)

        self._idx += 1

    def get_waveforms(self, window_sec: float = DISPLAY_WINDOW_SEC):
        """Return ordered arrays (oldest→newest) for the display window."""
        n = min(int(window_sec * self.fs), self._buf, self._idx)
        return self._slice(n)

    @property
    def snapshot(self) -> BreathingSnapshot:
        """Current numerical parameters (with slight noise)."""
        rnd = lambda v, s: float(v + np.random.normal(0, s))
        phi = (self._freq * self._t) % 1.0
        phase = _EELI_FLOOR + (1.0 - _EELI_FLOOR) * breath_phase_value(phi)

        r_pct = rnd(52.0, 0.5)
        l_pct = 100.0 - r_pct

        roi_pct = [rnd(a * 100 / sum(_ROI_AMP), 0.4) for a in _ROI_AMP]
        lr = sum(roi_pct[4:]) / max(sum(roi_pct[:4]), 1e-9)
        trends = self._compute_trends()

        return BreathingSnapshot(
            rr       = rnd(self.rr, 0.3),
            t_pct    = 100.0,
            r_pct    = r_pct,
            l_pct    = l_pct,
            lr_ratio = rnd(lr, 0.01),
            vd_ratio = rnd(0.85, 0.02),
            eeli     = rnd(0.45, 0.01),
            eili     = rnd(1.45, 0.01),
            tvi      = rnd(1.00, 0.03),
            phase    = phase,
            roi_pct  = roi_pct,
            trend_global = trends["global"],
            trend_r      = trends["r"],
            trend_l      = trends["l"],
            roi_trends   = trends["rois"],
        )

    # ── Internals ────────────────────────────────────────────────────────────

    def _breath_amp(self, t: float) -> float:
        """Slow breath-to-breath TVi drift (±4–8 %)."""
        n = self._freq * t
        return (1.0
                + 0.05 * np.sin(n * 0.63 + 0.4)
                + 0.04 * np.sin(n * 1.37 + 2.1))

    def _wave_noise(self) -> float:
        """Multiplicative sample noise: σ≈5 % of amplitude, |ε| ≤ 10 %."""
        return float(np.clip(
            np.random.normal(0, _WAVE_NOISE_STD), -_WAVE_NOISE_MAX, _WAVE_NOISE_MAX
        ))

    def _breath(self, t: float, amp: float = 1.0, phase: float = 0.0) -> float:
        return breath_waveform(t, self._freq, amp * self._breath_amp(t), phase)

    def _with_noise(self, v: float) -> float:
        return max(0.0, v * (1.0 + self._wave_noise()))

    def _global(self, t: float) -> float:
        return self._with_noise(self._breath(t, 1.0))

    def _roi(self, t: float, j: int) -> float:
        return self._with_noise(
            self._breath(t, _ROI_AMP[j] / 0.27, _ROI_PHASE[j])
        )

    def _prefill(self):
        """Fill buffer with data starting from t=-BUFFER_SEC."""
        n = self._buf
        t_start = -BUFFER_SEC
        for k in range(n):
            t = t_start + k * self._dt
            i = k % self._buf
            self._time_buf[i]   = t
            self._global_buf[i] = self._global(t)
            for j in range(8):
                self._roi_bufs[j][i] = self._roi(t, j)
        self._idx = n

    def _slice(self, n: int):
        """Extract n newest samples from ring buffer in chronological order."""
        start = (self._idx - n) % self._buf

        def extract(buf):
            if start + n <= self._buf:
                return buf[start : start + n].copy()
            return np.concatenate([buf[start:], buf[: n - (self._buf - start)]])

        return {
            "time":   extract(self._time_buf),
            "global": extract(self._global_buf),
            "rois":   [extract(b) for b in self._roi_bufs],
        }

    def _compute_trends(self, window: int = 50) -> dict:
        """Краткосрочный тренд (% изменения) по последним *window* отсчётам."""
        n = min(window, self._idx)
        if n < 2:
            zero = {"global": 0.0, "r": 0.0, "l": 0.0, "rois": [0.0] * 8}
            return zero

        waves = self._slice(n)
        rois = waves["rois"]

        def _trend(arr: np.ndarray) -> float:
            lo, hi = float(arr[0]), float(arr[-1])
            base = max(abs(lo), 0.05)
            return float(np.clip((hi - lo) / base * 100.0, -99.0, 99.0))

        r_agg = np.mean(rois[:4], axis=0)
        l_agg = np.mean(rois[4:], axis=0)
        return {
            "global": _trend(waves["global"]),
            "r":      _trend(r_agg),
            "l":      _trend(l_agg),
            "rois":   [_trend(r) for r in rois],
        }
