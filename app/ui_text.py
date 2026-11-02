"""Localized presentation of domain values that must not leak as raw codes."""

from __future__ import annotations

from .i18n import t


_QUALITY_KEYS = {
    "valid": "monitor_quality_valid",
    "degraded": "monitor_quality_degraded",
    "stale": "monitor_quality_stale",
    "unavailable": "monitor_quality_unavailable",
}

_QUALITY_REASON_KEYS = {
    "insufficient_data": "monitor_reason_insufficient",
    "insufficient_complete_cycles": "monitor_reason_cycles",
    "time_window_fallback": "monitor_reason_cycles",
    "no_detectable_breathing": "monitor_reason_no_breath",
    "regional_signal_unavailable": "monitor_reason_regional",
    "source_data_unavailable": "monitor_reason_source",
    "source_quality_degraded": "monitor_reason_source_quality",
    "reconstruction_assumptions_unconfirmed": "monitor_reason_reconstruction_hypothesis",
    "motion_or_signal_artifact": "monitor_reason_artifact",
    "monitoring_paused": "monitor_reason_paused",
    "data_stream_lost": "monitor_reason_lost",
}

_CONCLUSION_KEYS = {
    "operator_conclusion_not_provided": "study_conclusion_missing",
    "emergency_termination": "study_conclusion_emergency",
    "interrupted_by_application_restart": "study_conclusion_restart",
    "application_closed": "study_conclusion_application_closed",
    "monitoring_start_failed": "study_conclusion_start_failed",
}


def quality_text(value) -> str:
    code = getattr(value, "value", value)
    return t(_QUALITY_KEYS.get(str(code), "monitor_quality_unavailable"))


def quality_reason_text(reason: str | None) -> str:
    if not reason:
        return t("monitor_reason_unknown")
    return t(_QUALITY_REASON_KEYS.get(reason, "monitor_reason_unknown"))


def study_status_text(value) -> str:
    code = getattr(value, "value", value)
    key = f"study_status_{code}"
    translated = t(key)
    return translated if translated != f"[{key}]" else t("study_status_unknown")


def study_conclusion_text(value: str | None) -> str:
    if not value:
        return t("study_conclusion_missing")
    key = _CONCLUSION_KEYS.get(value)
    if key is not None:
        return t(key)
    # A clinician-authored conclusion is user data and should be preserved.
    return value

