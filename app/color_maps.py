"""Built-in colour maps shared by settings UI and EIT map rendering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ColorMap:
    id: str
    label_key: str
    low: str
    high: str


COLOR_MAPS: tuple[ColorMap, ...] = (
    ColorMap("medical_blue_amber", "color_map_medical_blue_amber", "#29b6d1", "#ffc857"),
    ColorMap("blue_red", "color_map_blue_red", "#2979ff", "#ff5252"),
    ColorMap("cyan_orange", "color_map_cyan_orange", "#00e5ff", "#ff9100"),
    ColorMap("teal_coral", "color_map_teal_coral", "#26a69a", "#ff6f61"),
    ColorMap("indigo_yellow", "color_map_indigo_yellow", "#536dfe", "#ffd740"),
    ColorMap("purple_lime", "color_map_purple_lime", "#ab47bc", "#c6ff00"),
    ColorMap("green_magenta", "color_map_green_magenta", "#00c853", "#ff4081"),
    ColorMap("navy_gold", "color_map_navy_gold", "#304ffe", "#ffab00"),
    ColorMap("ice_fire", "color_map_ice_fire", "#80d8ff", "#ff1744"),
    ColorMap("emerald_violet", "color_map_emerald_violet", "#00bfa5", "#7c4dff"),
    ColorMap("sky_rose", "color_map_sky_rose", "#40c4ff", "#f50057"),
    ColorMap("mint_ruby", "color_map_mint_ruby", "#69f0ae", "#d50000"),
    ColorMap("azure_tangerine", "color_map_azure_tangerine", "#448aff", "#ff6d00"),
    ColorMap("turquoise_pink", "color_map_turquoise_pink", "#1de9b6", "#ff80ab"),
    ColorMap("monochrome", "color_map_monochrome", "#90a4ae", "#ffffff"),
)

DEFAULT_COLOR_MAP_ID = COLOR_MAPS[0].id
CUSTOM_COLOR_MAP_ID = "custom"


def color_map_by_id(color_map_id: str) -> ColorMap | None:
    return next((item for item in COLOR_MAPS if item.id == color_map_id), None)


def resolve_color_map(
    color_map_id: str,
    custom_low: str,
    custom_high: str,
) -> tuple[str, str]:
    if color_map_id == CUSTOM_COLOR_MAP_ID:
        return custom_low, custom_high
    selected = color_map_by_id(color_map_id) or COLOR_MAPS[0]
    return selected.low, selected.high
