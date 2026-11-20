"""Persistent engineering-mode settings shared by UI and calculations."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .events import ApplicationEvent, EventBus, EventType
from .ports import SettingsRepository
from ..reconstruction.geometry import GeometryProfile, geometry_profile


ENGINEERING_SETTINGS_KEY = "engineering_settings"
INTERFACE_ELEMENTS_VERSION = 6
WORK_MODES = ("adult", "infant", "ventilation")
MIN_ROI_COUNT = 2
MAX_ROI_COUNT = 20
DEFAULT_ROI_COUNT = 8
PEAK_DETECTION_METHODS = ("mad_mean", "derivative", "legacy")
DEFAULT_PEAK_DETECTION_METHOD = "mad_mean"
BREATHING_IDENTIFICATION_METHODS = ("model", "spectral")
DEFAULT_BREATHING_IDENTIFICATION_METHOD = "model"
MIN_GRAPH_DISPLAY_PERIOD_SECONDS = 10
MAX_GRAPH_DISPLAY_PERIOD_SECONDS = 120
DEFAULT_GRAPH_DISPLAY_PERIOD_SECONDS = 60
DEFAULT_APPLICATION_BACKGROUND_COLOR = "#0d1117"
TREND_POINT_MODES = ("interval", "breath_cycle")
DEFAULT_TREND_POINT_MODE = "interval"
TREND_DOWNSAMPLING_MODES = ("none", "manual_adult", "manual_infant")
DEFAULT_TREND_DOWNSAMPLING_MODE = "manual_adult"
TREND_CHART_MODES = ("bars", "lines")
DEFAULT_TREND_CHART_MODE = "bars"
MIN_TREND_DECIMAL_PLACES = 0
MAX_TREND_DECIMAL_PLACES = 3
DEFAULT_TREND_DECIMAL_PLACES = 0
BASE_TREND_METRIC_CODES = (
    "eeli_au", "eili_au", "tvi_au", "mli_au", "mvi_au_per_min", "rr_bpm",
    "right_left_ratio", "ventral_dorsal_ratio", "right_percent", "left_percent",
)
SUPPORTED_TREND_METRIC_CODES = BASE_TREND_METRIC_CODES + tuple(
    code
    for index in range(1, MAX_ROI_COUNT + 1)
    for code in (f"roi_{index}_tvi_au", f"roi_{index}_percent")
)
AERATION_METRIC_CODES = ("total_percent",) + SUPPORTED_TREND_METRIC_CODES
MIN_PEEP_SILENT_THRESHOLD_PERCENT = 1
MAX_PEEP_SILENT_THRESHOLD_PERCENT = 30
DEFAULT_PEEP_SILENT_THRESHOLD_PERCENT = 10
MIN_PEEP_ANALYSIS_INTERVAL_SECONDS = 5
MAX_PEEP_ANALYSIS_INTERVAL_SECONDS = 60
DEFAULT_PEEP_ANALYSIS_INTERVAL_SECONDS = 15
INTERFACE_TABS = (
    "main",
    "express_monitoring",
    "patient",
    "trends",
    "analysis",
    "peep",
    "eit_settings",
    "reports",
    "export",
    "service",
    "system",
    "debug",
)
REQUIRED_INTERFACE_TABS = ("main", "system")
INTERFACE_ELEMENTS: dict[str, tuple[str, ...]] = {
    "main": (
        "main.quality", "main.lung_map", "main.total", "main.regional",
        "main.rl", "main.vd", "main.tvi", "main.eeli", "main.eili", "main.mvi",
        "main.global_waveform", "main.regional_waveforms",
        "main.velocity", "main.respiratory_rate", "main.trends", "main.controls",
    ),
    "express_monitoring": (
        "express_monitoring.lung_map",
        "express_monitoring.plethysmogram",
        "express_monitoring.metrics",
    ),
    "patient": (
        "patient.card", "patient.clinical", "patient.history", "patient.controls",
    ),
    "trends": (
        "trends.tabs", "trends.period", "trends.charts", "trends.controls",
    ),
    "analysis": (
        "analysis.tabs", "analysis.lung_map", "analysis.metrics",
        "analysis.waveforms", "analysis.classification", "analysis.controls",
    ),
    "peep": ("peep.map", "peep.metrics", "peep.controls"),
    "eit_settings": (
        "eit_settings.acquisition", "eit_settings.visualization",
        "eit_settings.pathology", "eit_settings.diagnosis", "eit_settings.controls",
    ),
    "reports": (
        "reports.saved", "reports.form", "reports.preview", "reports.controls",
    ),
    "export": (
        "export.format", "export.categories", "export.history",
        "export.summary", "export.controls",
    ),
    "service": (
        "service.title", "service.filters", "service.events", "service.controls",
    ),
    "system": ("system.title", "system.information"),
    "debug": (
        "debug.duration", "debug.diagram", "debug.chart",
        "debug.status", "debug.controls",
    ),
}
ALL_INTERFACE_ELEMENTS = tuple(
    element
    for tab in INTERFACE_TABS
    for element in INTERFACE_ELEMENTS[tab]
)


@dataclass(frozen=True, slots=True)
class EngineeringSettings:
    work_modes: tuple[str, ...] = ("adult",)
    roi_count: int = DEFAULT_ROI_COUNT
    peak_detection_method: str = DEFAULT_PEAK_DETECTION_METHOD
    visible_tabs: tuple[str, ...] = INTERFACE_TABS
    show_main_trends: bool = True
    show_main_tvi: bool = True
    visible_elements: tuple[str, ...] = ALL_INTERFACE_ELEMENTS
    graph_display_period_seconds: int = DEFAULT_GRAPH_DISPLAY_PERIOD_SECONDS
    trend_point_mode: str = DEFAULT_TREND_POINT_MODE
    trend_downsampling_mode: str = DEFAULT_TREND_DOWNSAMPLING_MODE
    peep_silent_threshold_percent: int = DEFAULT_PEEP_SILENT_THRESHOLD_PERCENT
    peep_analysis_interval_seconds: int = DEFAULT_PEEP_ANALYSIS_INTERVAL_SECONDS
    peep_gravity_angle_degrees: int = 0
    section_profile: GeometryProfile = field(
        default_factory=lambda: geometry_profile("adult_ellipse")
    )
    custom_section_profiles: tuple[GeometryProfile, ...] = ()
    trend_chart_mode: str = DEFAULT_TREND_CHART_MODE
    breathing_identification_method: str = DEFAULT_BREATHING_IDENTIFICATION_METHOD
    application_background_color: str = DEFAULT_APPLICATION_BACKGROUND_COLOR
    waveform_fill_enabled: bool = True
    trend_decimal_places: int = DEFAULT_TREND_DECIMAL_PLACES
    hidden_trend_metrics: tuple[str, ...] = ()
    hidden_aeration_metrics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized = tuple(dict.fromkeys(self.work_modes))
        if not normalized:
            raise ValueError("at least one work mode must be enabled")
        if any(mode not in WORK_MODES for mode in normalized):
            raise ValueError("unsupported work mode")
        if normalized != self.work_modes:
            raise ValueError("work modes must be unique")
        if (
            isinstance(self.roi_count, bool)
            or not isinstance(self.roi_count, int)
            or not MIN_ROI_COUNT <= self.roi_count <= MAX_ROI_COUNT
            or self.roi_count % 2
        ):
            raise ValueError("roi_count must be an even integer from 2 to 20")
        if self.peak_detection_method not in PEAK_DETECTION_METHODS:
            raise ValueError("unsupported peak_detection_method")
        if self.breathing_identification_method not in BREATHING_IDENTIFICATION_METHODS:
            raise ValueError("unsupported breathing_identification_method")
        if (
            not isinstance(self.application_background_color, str)
            or re.fullmatch(r"#[0-9a-fA-F]{6}", self.application_background_color) is None
        ):
            raise ValueError("application_background_color must use #RRGGBB format")
        object.__setattr__(
            self, "application_background_color", self.application_background_color.lower()
        )
        if not isinstance(self.waveform_fill_enabled, bool):
            raise ValueError("waveform_fill_enabled must be a boolean")
        if self.trend_point_mode not in TREND_POINT_MODES:
            raise ValueError("unsupported trend_point_mode")
        if self.trend_downsampling_mode not in TREND_DOWNSAMPLING_MODES:
            raise ValueError("unsupported trend_downsampling_mode")
        if self.trend_chart_mode not in TREND_CHART_MODES:
            raise ValueError("unsupported trend_chart_mode")
        if (
            isinstance(self.trend_decimal_places, bool)
            or not isinstance(self.trend_decimal_places, int)
            or not MIN_TREND_DECIMAL_PLACES
            <= self.trend_decimal_places
            <= MAX_TREND_DECIMAL_PLACES
        ):
            raise ValueError("trend_decimal_places must be an integer from 0 to 3")
        normalized_hidden_metrics = tuple(dict.fromkeys(self.hidden_trend_metrics))
        if normalized_hidden_metrics != self.hidden_trend_metrics:
            raise ValueError("hidden_trend_metrics must be unique")
        if any(
            not isinstance(code, str) or code not in SUPPORTED_TREND_METRIC_CODES
            for code in normalized_hidden_metrics
        ):
            raise ValueError("unsupported hidden trend metric")
        normalized_hidden_aeration = tuple(
            dict.fromkeys(self.hidden_aeration_metrics)
        )
        if normalized_hidden_aeration != self.hidden_aeration_metrics:
            raise ValueError("hidden_aeration_metrics must be unique")
        if any(
            not isinstance(code, str) or code not in AERATION_METRIC_CODES
            for code in normalized_hidden_aeration
        ):
            raise ValueError("unsupported hidden aeration metric")
        if (
            isinstance(self.peep_silent_threshold_percent, bool)
            or not isinstance(self.peep_silent_threshold_percent, int)
            or not MIN_PEEP_SILENT_THRESHOLD_PERCENT
            <= self.peep_silent_threshold_percent
            <= MAX_PEEP_SILENT_THRESHOLD_PERCENT
        ):
            raise ValueError("PEEP silent-space threshold must be an integer from 1 to 30")
        if (
            isinstance(self.peep_analysis_interval_seconds, bool)
            or not isinstance(self.peep_analysis_interval_seconds, int)
            or not MIN_PEEP_ANALYSIS_INTERVAL_SECONDS
            <= self.peep_analysis_interval_seconds
            <= MAX_PEEP_ANALYSIS_INTERVAL_SECONDS
        ):
            raise ValueError("PEEP analysis interval must be an integer from 5 to 60")
        if (
            isinstance(self.peep_gravity_angle_degrees, bool)
            or not isinstance(self.peep_gravity_angle_degrees, int)
            or not -180 <= self.peep_gravity_angle_degrees <= 180
        ):
            raise ValueError("PEEP gravity angle must be an integer from -180 to 180")
        if not isinstance(self.section_profile, GeometryProfile):
            raise ValueError("section_profile must be a GeometryProfile")
        if any(
            not isinstance(profile, GeometryProfile)
            for profile in self.custom_section_profiles
        ):
            raise ValueError("custom_section_profiles must contain GeometryProfile values")
        profile_ids = tuple(
            profile.profile_id for profile in self.custom_section_profiles
        )
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("custom section profile ids must be unique")
        if (
            isinstance(self.graph_display_period_seconds, bool)
            or not isinstance(self.graph_display_period_seconds, int)
            or not MIN_GRAPH_DISPLAY_PERIOD_SECONDS
            <= self.graph_display_period_seconds
            <= MAX_GRAPH_DISPLAY_PERIOD_SECONDS
        ):
            raise ValueError("graph_display_period_seconds must be an integer from 10 to 120")
        normalized_tabs = tuple(dict.fromkeys(self.visible_tabs))
        if normalized_tabs != self.visible_tabs:
            raise ValueError("visible_tabs must be unique")
        if any(tab not in INTERFACE_TABS for tab in normalized_tabs):
            raise ValueError("unsupported interface tab")
        if any(tab not in normalized_tabs for tab in REQUIRED_INTERFACE_TABS):
            raise ValueError("main and system tabs must remain visible")
        if not isinstance(self.show_main_trends, bool):
            raise ValueError("show_main_trends must be a boolean")
        if not isinstance(self.show_main_tvi, bool):
            raise ValueError("show_main_tvi must be a boolean")
        requested_elements = self.visible_elements
        normalized_elements = tuple(dict.fromkeys(requested_elements))
        if normalized_elements != requested_elements:
            raise ValueError("visible_elements must be unique")
        if any(element not in ALL_INTERFACE_ELEMENTS for element in normalized_elements):
            raise ValueError("unsupported interface element")
        # Preserve the two legacy flags while callers migrate to visible_elements.
        if not self.show_main_trends:
            normalized_elements = tuple(
                element for element in normalized_elements if element != "main.trends"
            )
        if not self.show_main_tvi:
            normalized_elements = tuple(
                element for element in normalized_elements if element != "main.tvi"
            )
        object.__setattr__(self, "visible_elements", normalized_elements)

    def to_payload(self) -> dict[str, object]:
        return {
            "work_modes": list(self.work_modes),
            "roi_count": self.roi_count,
            "peak_detection_method": self.peak_detection_method,
            "breathing_identification_method": self.breathing_identification_method,
            "application_background_color": self.application_background_color,
            "waveform_fill_enabled": self.waveform_fill_enabled,
            "visible_tabs": list(self.visible_tabs),
            "show_main_trends": self.show_main_trends,
            "show_main_tvi": self.show_main_tvi,
            "visible_elements": list(self.visible_elements),
            "interface_elements_version": INTERFACE_ELEMENTS_VERSION,
            "graph_display_period_seconds": self.graph_display_period_seconds,
            "trend_point_mode": self.trend_point_mode,
            "trend_downsampling_mode": self.trend_downsampling_mode,
            "trend_chart_mode": self.trend_chart_mode,
            "trend_decimal_places": self.trend_decimal_places,
            "hidden_trend_metrics": list(self.hidden_trend_metrics),
            "hidden_aeration_metrics": list(self.hidden_aeration_metrics),
            "peep_silent_threshold_percent": self.peep_silent_threshold_percent,
            "peep_analysis_interval_seconds": self.peep_analysis_interval_seconds,
            "peep_gravity_angle_degrees": self.peep_gravity_angle_degrees,
            "section_profile": self.section_profile.to_dict(),
            "custom_section_profiles": [
                profile.to_dict() for profile in self.custom_section_profiles
            ],
        }

    @classmethod
    def from_payload(cls, payload: object) -> "EngineeringSettings":
        if not isinstance(payload, dict):
            raise ValueError("stored engineering settings must be an object")
        modes = payload.get("work_modes", ["adult"])
        if not isinstance(modes, list) or not all(isinstance(item, str) for item in modes):
            raise ValueError("stored work_modes must be a string list")
        visible_tabs = payload.get("visible_tabs", list(INTERFACE_TABS))
        if not isinstance(visible_tabs, list) or not all(
            isinstance(item, str) for item in visible_tabs
        ):
            raise ValueError("stored visible_tabs must be a string list")
        visible_elements = payload.get("visible_elements")
        if visible_elements is None:
            visible_elements = list(ALL_INTERFACE_ELEMENTS)
            if not payload.get("show_main_trends", True):
                visible_elements.remove("main.trends")
            if not payload.get("show_main_tvi", True):
                visible_elements.remove("main.tvi")
        if not isinstance(visible_elements, list) or not all(
            isinstance(item, str) for item in visible_elements
        ):
            raise ValueError("stored visible_elements must be a string list")
        hidden_trend_metrics = payload.get("hidden_trend_metrics", [])
        if not isinstance(hidden_trend_metrics, list) or not all(
            isinstance(item, str) for item in hidden_trend_metrics
        ):
            raise ValueError("stored hidden_trend_metrics must be a string list")
        hidden_aeration_metrics = payload.get("hidden_aeration_metrics", [])
        if not isinstance(hidden_aeration_metrics, list) or not all(
            isinstance(item, str) for item in hidden_aeration_metrics
        ):
            raise ValueError("stored hidden_aeration_metrics must be a string list")
        legacy_peep_visible = "analysis.peep_tab" in visible_elements
        visible_elements = [
            item for item in visible_elements if item != "analysis.peep_tab"
        ]
        interface_elements_version = payload.get("interface_elements_version", 1)
        if (
            isinstance(interface_elements_version, bool)
            or not isinstance(interface_elements_version, int)
        ):
            raise ValueError("stored interface_elements_version must be an integer")
        if (
            interface_elements_version < INTERFACE_ELEMENTS_VERSION
            and "main.mvi" not in visible_elements
        ):
            visible_elements.append("main.mvi")
        if interface_elements_version < 3 and "main.velocity" not in visible_elements:
            visible_elements.append("main.velocity")
        if interface_elements_version < 4:
            legacy_peep_visible = True
        if interface_elements_version < 5 and legacy_peep_visible:
            for element in INTERFACE_ELEMENTS["peep"]:
                if element not in visible_elements:
                    visible_elements.append(element)
            if "peep" not in visible_tabs and "analysis" in visible_tabs:
                analysis_index = visible_tabs.index("analysis")
                visible_tabs.insert(analysis_index + 1, "peep")
        elif interface_elements_version < 5 and "peep" in visible_tabs:
            visible_tabs.remove("peep")
        if interface_elements_version < 6:
            for element in INTERFACE_ELEMENTS["express_monitoring"]:
                if element not in visible_elements:
                    visible_elements.append(element)
            if "express_monitoring" not in visible_tabs:
                main_index = visible_tabs.index("main") if "main" in visible_tabs else -1
                visible_tabs.insert(main_index + 1, "express_monitoring")
        section_payload = payload.get("section_profile")
        section_profile = (
            geometry_profile("adult_ellipse")
            if section_payload is None
            else GeometryProfile.from_dict(section_payload)
        )
        custom_payloads = payload.get("custom_section_profiles", [])
        if not isinstance(custom_payloads, list):
            raise ValueError("stored custom_section_profiles must be a list")
        custom_profiles = tuple(
            GeometryProfile.from_dict(item) for item in custom_payloads
        )
        return cls(
            tuple(modes),
            payload.get("roi_count", DEFAULT_ROI_COUNT),
            payload.get("peak_detection_method", DEFAULT_PEAK_DETECTION_METHOD),
            tuple(visible_tabs),
            payload.get("show_main_trends", True),
            payload.get("show_main_tvi", True),
            tuple(visible_elements),
            payload.get(
                "graph_display_period_seconds",
                DEFAULT_GRAPH_DISPLAY_PERIOD_SECONDS,
            ),
            payload.get("trend_point_mode", DEFAULT_TREND_POINT_MODE),
            payload.get(
                "trend_downsampling_mode",
                DEFAULT_TREND_DOWNSAMPLING_MODE,
            ),
            payload.get(
                "peep_silent_threshold_percent",
                DEFAULT_PEEP_SILENT_THRESHOLD_PERCENT,
            ),
            payload.get(
                "peep_analysis_interval_seconds",
                DEFAULT_PEEP_ANALYSIS_INTERVAL_SECONDS,
            ),
            payload.get("peep_gravity_angle_degrees", 0),
            section_profile,
            custom_profiles,
            payload.get("trend_chart_mode", DEFAULT_TREND_CHART_MODE),
            payload.get(
                "breathing_identification_method",
                DEFAULT_BREATHING_IDENTIFICATION_METHOD,
            ),
            payload.get(
                "application_background_color",
                DEFAULT_APPLICATION_BACKGROUND_COLOR,
            ),
            payload.get("waveform_fill_enabled", True),
            payload.get("trend_decimal_places", DEFAULT_TREND_DECIMAL_PLACES),
            tuple(hidden_trend_metrics),
            tuple(hidden_aeration_metrics),
        )

    def is_element_visible(self, element: str) -> bool:
        return element in self.visible_elements

    def is_trend_metric_visible(self, code: str) -> bool:
        return code not in self.hidden_trend_metrics

    def is_aeration_metric_visible(self, code: str) -> bool:
        """Return whether a calculated aeration parameter is shown anywhere."""
        return code not in self.hidden_aeration_metrics


class EngineeringSettingsService:
    def __init__(self, repository: SettingsRepository, event_bus: EventBus) -> None:
        self._repository = repository
        self._event_bus = event_bus
        self._listeners: list[Callable[[EngineeringSettings], None]] = []
        self._current = self._load()

    @property
    def current(self) -> EngineeringSettings:
        return self._current

    def save(self, settings: EngineeringSettings) -> EngineeringSettings:
        if not isinstance(settings, EngineeringSettings):
            raise TypeError("settings must be EngineeringSettings")
        self._repository.save({ENGINEERING_SETTINGS_KEY: settings.to_payload()})
        self._current = settings
        self._event_bus.publish(ApplicationEvent(
            EventType.SETTINGS_CHANGED,
            payload={ENGINEERING_SETTINGS_KEY: settings.to_payload()},
        ))
        for listener in tuple(self._listeners):
            listener(settings)
        return settings

    def subscribe(
        self, listener: Callable[[EngineeringSettings], None]
    ) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _load(self) -> EngineeringSettings:
        payload = self._repository.load().get(ENGINEERING_SETTINGS_KEY)
        return EngineeringSettings() if payload is None else EngineeringSettings.from_payload(payload)
