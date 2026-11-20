"""Профили геометрии поперечного сечения для 2D-модели ЭИТ."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any, Mapping


CONTOUR_SAMPLE_COUNT = 64
LUNG_CONTOUR_SAMPLE_COUNT = 32


def _default_lung_factors() -> tuple[float, ...]:
    return (1.0,) * LUNG_CONTOUR_SAMPLE_COUNT


@dataclass(frozen=True)
class GeometryProfile:
    """Звездообразный 2D-контур и номинальные параметры электродов.

    ``boundary_radius_factors`` задаёт безразмерный радиус контура через
    равномерные угловые отсчёты. Пустой кортеж означает окружность. Такой
    контракт позволяет позднее подключить извлечённый из КТ/МРТ контур без
    изменения КЭ-решателя, если контур звездообразен относительно начала.

    Размеры встроенных профилей являются инженерными настройками прототипа,
    а не антропометрической или клинической нормой.
    """

    profile_id: str
    display_name: str
    radius_m: float
    electrode_width_fraction: float = 0.75
    contact_impedance_ohm_m: float = 0.01
    background_conductivity_s_m: float = 1.0
    boundary_radius_factors: tuple[float, ...] = ()
    clinically_validated: bool = False
    physical_parameters_confirmed: bool = False
    source_reference: str | None = None
    shape_kind: str = "circle"
    width_m: float | None = None
    height_m: float | None = None
    rotation_degrees: float = 0.0
    lungs_enabled: bool = True
    left_lung_radius_factors: tuple[float, ...] = ()
    right_lung_radius_factors: tuple[float, ...] = ()
    left_lung_center: tuple[float, float] = (0.28, 0.0)
    right_lung_center: tuple[float, float] = (-0.28, 0.0)

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("Идентификатор профиля геометрии не может быть пустым")
        for label, value in (
            ("Радиус", self.radius_m),
            ("Контактный импеданс", self.contact_impedance_ohm_m),
            ("Фоновая проводимость", self.background_conductivity_s_m),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{label} должен быть положительным конечным числом")
        if not 0 < self.electrode_width_fraction <= 1:
            raise ValueError("Доля ширины электрода должна лежать в диапазоне (0, 1]")
        if self.boundary_radius_factors:
            if len(self.boundary_radius_factors) < 16:
                raise ValueError("Реалистичный контур требует не менее 16 отсчётов")
            if any(not math.isfinite(v) or v <= 0 for v in self.boundary_radius_factors):
                raise ValueError("Радиальные коэффициенты контура должны быть положительными")
        if self.physical_parameters_confirmed and not (
            self.source_reference and self.source_reference.strip()
        ):
            raise ValueError(
                "Подтверждённая геометрия требует ссылку на первичный источник"
            )
        if self.shape_kind not in {"circle", "ellipse", "radial"}:
            raise ValueError("Неизвестный тип контура")
        if self.shape_kind == "ellipse":
            if self.width_m is None or self.height_m is None:
                raise ValueError("Эллипс требует ширину и высоту")
            if self.width_m <= 0 or self.height_m <= 0:
                raise ValueError("Размеры эллипса должны быть положительными")
        if not math.isfinite(self.rotation_degrees):
            raise ValueError("Поворот контура должен быть конечным")
        if not isinstance(self.lungs_enabled, bool):
            raise ValueError("Флаг отображения лёгких должен быть boolean")
        for label, factors in (
            ("левого лёгкого", self.left_lung_radius_factors),
            ("правого лёгкого", self.right_lung_radius_factors),
        ):
            if factors and len(factors) != LUNG_CONTOUR_SAMPLE_COUNT:
                raise ValueError(
                    f"Контур {label} должен содержать "
                    f"{LUNG_CONTOUR_SAMPLE_COUNT} отсчёта"
                )
            if any(not math.isfinite(v) or not 0.35 <= v <= 1.45 for v in factors):
                raise ValueError(
                    f"Радиальные коэффициенты {label} должны лежать в диапазоне [0.35, 1.45]"
                )
        for label, center in (
            ("левого лёгкого", self.left_lung_center),
            ("правого лёгкого", self.right_lung_center),
        ):
            if len(center) != 2 or any(
                not math.isfinite(value) or abs(value) > 1.5 for value in center
            ):
                raise ValueError(
                    f"Центр {label} должен содержать две конечные координаты "
                    "в диапазоне [-1.5, 1.5]"
                )

    def radius_at(self, angle_radians: float) -> float:
        """Радиус границы с периодической линейной интерполяцией."""

        if not self.boundary_radius_factors:
            return self.radius_m
        factors = self.boundary_radius_factors
        position = (angle_radians % (2 * math.pi)) * len(factors) / (2 * math.pi)
        left = int(math.floor(position)) % len(factors)
        fraction = position - math.floor(position)
        right = (left + 1) % len(factors)
        factor = factors[left] * (1 - fraction) + factors[right] * fraction
        return self.radius_m * factor

    def with_contour(
        self,
        boundary_radius_factors: tuple[float, ...],
        *,
        profile_id: str,
        display_name: str,
    ) -> "GeometryProfile":
        """Создать профиль пользовательского звездообразного контура."""

        return replace(
            self,
            profile_id=profile_id,
            display_name=display_name,
            boundary_radius_factors=tuple(float(v) for v in boundary_radius_factors),
            clinically_validated=False,
            physical_parameters_confirmed=False,
            source_reference=None,
            shape_kind="radial",
            width_m=None,
            height_m=None,
            rotation_degrees=0.0,
        )

    def with_identity(self, *, profile_id: str, display_name: str) -> "GeometryProfile":
        """Copy a preset without discarding its parametric ellipse metadata."""

        return replace(
            self,
            profile_id=profile_id,
            display_name=display_name,
            clinically_validated=False,
            physical_parameters_confirmed=False,
            source_reference=None,
        )

    def lung_radius_factors(self, side: str) -> tuple[float, ...]:
        """Return the editable normalized contour for one anatomical lung."""

        if side == "left":
            return self.left_lung_radius_factors or _default_lung_factors()
        if side == "right":
            return self.right_lung_radius_factors or _default_lung_factors()
        raise ValueError("side must be 'left' or 'right'")

    def lung_point(self, side: str, index: int) -> tuple[float, float]:
        """Return a lung contour point in the physical section coordinates."""

        factors = self.lung_radius_factors(side)
        angle = 2.0 * math.pi * (index % len(factors)) / len(factors)
        center_x, center_y = self.lung_center(side)
        factor = factors[index % len(factors)]
        return (
            self.radius_m * (center_x + 0.235 * factor * math.cos(angle)),
            self.radius_m * (center_y + 0.46 * factor * math.sin(angle)),
        )

    def lung_center(self, side: str) -> tuple[float, float]:
        """Return the normalized physical center of one lung."""

        if side == "left":
            return self.left_lung_center
        if side == "right":
            return self.right_lung_center
        raise ValueError("side must be 'left' or 'right'")

    def _lung_fits_at(self, side: str, center: tuple[float, float]) -> bool:
        factors = self.lung_radius_factors(side)
        center_x, center_y = center
        for index, factor in enumerate(factors):
            angle = 2.0 * math.pi * index / len(factors)
            x = self.radius_m * (
                center_x + 0.235 * factor * math.cos(angle)
            )
            y = self.radius_m * (
                center_y + 0.46 * factor * math.sin(angle)
            )
            point_radius = math.hypot(x, y)
            point_angle = math.atan2(y, x)
            if point_radius > self.radius_at(point_angle) * 0.995:
                return False
        return True

    def constrained_lung_center(
        self, side: str, requested: tuple[float, float]
    ) -> tuple[float, float]:
        """Clamp a requested lung translation to the section boundary."""

        target = tuple(float(value) for value in requested)
        if len(target) != 2 or any(not math.isfinite(value) for value in target):
            raise ValueError("Центр лёгкого должен содержать две конечные координаты")
        if self._lung_fits_at(side, target):
            return target

        current = self.lung_center(side)
        anchor = current if self._lung_fits_at(side, current) else (0.0, 0.0)
        if not self._lung_fits_at(side, anchor):
            return current
        low, high = 0.0, 1.0
        for _ in range(32):
            fraction = (low + high) / 2.0
            candidate = (
                anchor[0] + (target[0] - anchor[0]) * fraction,
                anchor[1] + (target[1] - anchor[1]) * fraction,
            )
            if self._lung_fits_at(side, candidate):
                low = fraction
            else:
                high = fraction
        return (
            anchor[0] + (target[0] - anchor[0]) * low,
            anchor[1] + (target[1] - anchor[1]) * low,
        )

    def with_lung_center(
        self, side: str, center: tuple[float, float]
    ) -> "GeometryProfile":
        """Move one lung while keeping its complete contour inside the section."""

        value = self.constrained_lung_center(side, center)
        if side == "left":
            return replace(self, left_lung_center=value)
        if side == "right":
            return replace(self, right_lung_center=value)
        raise ValueError("side must be 'left' or 'right'")

    def with_lung_contour(
        self, side: str, radius_factors: tuple[float, ...]
    ) -> "GeometryProfile":
        """Replace one lung contour while preserving the section geometry."""

        values = tuple(float(value) for value in radius_factors)
        if side == "left":
            return replace(self, left_lung_radius_factors=values)
        if side == "right":
            return replace(self, right_lung_radius_factors=values)
        raise ValueError("side must be 'left' or 'right'")

    def with_lungs_enabled(self, enabled: bool) -> "GeometryProfile":
        return replace(self, lungs_enabled=bool(enabled))

    def to_dict(self) -> dict[str, Any]:
        """Serialize a profile for engineering settings and study snapshots."""

        return {
            "profile_id": self.profile_id,
            "display_name": self.display_name,
            "radius_m": self.radius_m,
            "electrode_width_fraction": self.electrode_width_fraction,
            "contact_impedance_ohm_m": self.contact_impedance_ohm_m,
            "background_conductivity_s_m": self.background_conductivity_s_m,
            "boundary_radius_factors": list(self.boundary_radius_factors),
            "clinically_validated": self.clinically_validated,
            "physical_parameters_confirmed": self.physical_parameters_confirmed,
            "source_reference": self.source_reference,
            "shape_kind": self.shape_kind,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "rotation_degrees": self.rotation_degrees,
            "lungs_enabled": self.lungs_enabled,
            "left_lung_radius_factors": list(self.left_lung_radius_factors),
            "right_lung_radius_factors": list(self.right_lung_radius_factors),
            "left_lung_center": list(self.left_lung_center),
            "right_lung_center": list(self.right_lung_center),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GeometryProfile":
        """Прочитать подтверждаемую геометрию из профиля прибора."""

        if not isinstance(payload, Mapping):
            raise ValueError("Раздел geometry должен быть объектом")

        def text(name: str) -> str:
            value = payload.get(name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"geometry.{name} должен быть непустой строкой")
            return value.strip()

        def number(name: str) -> float:
            value = payload.get(name)
            if isinstance(value, bool):
                raise ValueError(f"geometry.{name} должен быть числом")
            try:
                return float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"geometry.{name} должен быть числом") from exc

        factors = payload.get("boundary_radius_factors", [])
        if not isinstance(factors, list):
            raise ValueError("geometry.boundary_radius_factors должен быть массивом")
        confirmed = payload.get("physical_parameters_confirmed", False)
        clinically_validated = payload.get("clinically_validated", False)
        if not isinstance(confirmed, bool) or not isinstance(clinically_validated, bool):
            raise ValueError("Флаги подтверждения geometry должны быть boolean")
        source_reference = payload.get("source_reference")
        if source_reference is not None and (
            not isinstance(source_reference, str) or not source_reference.strip()
        ):
            raise ValueError("geometry.source_reference должен быть непустой строкой")
        try:
            factor_values = tuple(float(value) for value in factors)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "geometry.boundary_radius_factors должен содержать числа"
            ) from exc
        lung_factor_values: dict[str, tuple[float, ...]] = {}
        for field_name in (
            "left_lung_radius_factors",
            "right_lung_radius_factors",
        ):
            raw_values = payload.get(field_name, [])
            if not isinstance(raw_values, list):
                raise ValueError(f"geometry.{field_name} должен быть массивом")
            try:
                lung_factor_values[field_name] = tuple(
                    float(value) for value in raw_values
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"geometry.{field_name} должен содержать числа"
                ) from exc
        lungs_enabled = payload.get("lungs_enabled", True)
        if not isinstance(lungs_enabled, bool):
            raise ValueError("geometry.lungs_enabled должен быть boolean")
        lung_centers: dict[str, tuple[float, float]] = {}
        for field_name, default in (
            ("left_lung_center", (0.28, 0.0)),
            ("right_lung_center", (-0.28, 0.0)),
        ):
            raw_center = payload.get(field_name, default)
            if not isinstance(raw_center, (list, tuple)) or len(raw_center) != 2:
                raise ValueError(f"geometry.{field_name} должен содержать две координаты")
            try:
                lung_centers[field_name] = (
                    float(raw_center[0]), float(raw_center[1])
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"geometry.{field_name} должен содержать числа"
                ) from exc
        return cls(
            profile_id=text("profile_id"),
            display_name=text("display_name"),
            radius_m=number("radius_m"),
            electrode_width_fraction=number("electrode_width_fraction"),
            contact_impedance_ohm_m=number("contact_impedance_ohm_m"),
            background_conductivity_s_m=number("background_conductivity_s_m"),
            boundary_radius_factors=factor_values,
            clinically_validated=clinically_validated,
            physical_parameters_confirmed=confirmed,
            source_reference=(
                source_reference.strip() if isinstance(source_reference, str) else None
            ),
            shape_kind=str(payload.get(
                "shape_kind", "radial" if factor_values else "circle"
            )),
            width_m=(
                None if payload.get("width_m") is None else number("width_m")
            ),
            height_m=(
                None if payload.get("height_m") is None else number("height_m")
            ),
            rotation_degrees=float(payload.get("rotation_degrees", 0.0)),
            lungs_enabled=lungs_enabled,
            left_lung_radius_factors=lung_factor_values["left_lung_radius_factors"],
            right_lung_radius_factors=lung_factor_values["right_lung_radius_factors"],
            left_lung_center=lung_centers["left_lung_center"],
            right_lung_center=lung_centers["right_lung_center"],
        )

    def cache_key(self) -> tuple:
        return (
            self.profile_id,
            self.radius_m,
            self.electrode_width_fraction,
            self.contact_impedance_ohm_m,
            self.background_conductivity_s_m,
            self.boundary_radius_factors,
            self.clinically_validated,
            self.physical_parameters_confirmed,
            self.source_reference,
            self.shape_kind,
            self.width_m,
            self.height_m,
            self.rotation_degrees,
            self.lungs_enabled,
            self.left_lung_radius_factors,
            self.right_lung_radius_factors,
            self.left_lung_center,
            self.right_lung_center,
        )


def ellipse_profile(
    *,
    width_m: float,
    height_m: float,
    rotation_degrees: float = 0.0,
    profile_id: str = "custom-ellipse-v1",
    display_name: str = "Пользовательский эллипс",
    sample_count: int = CONTOUR_SAMPLE_COUNT,
    lungs_enabled: bool = True,
    left_lung_radius_factors: tuple[float, ...] = (),
    right_lung_radius_factors: tuple[float, ...] = (),
    left_lung_center: tuple[float, float] = (0.28, 0.0),
    right_lung_center: tuple[float, float] = (-0.28, 0.0),
) -> GeometryProfile:
    """Create a star-shaped radial representation of a rotated ellipse."""

    if not math.isfinite(width_m) or not math.isfinite(height_m):
        raise ValueError("Размеры эллипса должны быть конечными")
    if width_m <= 0 or height_m <= 0:
        raise ValueError("Размеры эллипса должны быть положительными")
    if sample_count < 16 or sample_count % 16:
        raise ValueError("Число отсчётов эллипса должно делиться на 16")
    semi_x, semi_y = width_m / 2.0, height_m / 2.0
    radius_m = max(semi_x, semi_y)
    rotation = math.radians(rotation_degrees)
    factors = []
    for index in range(sample_count):
        angle = 2.0 * math.pi * index / sample_count - rotation
        denominator = math.sqrt(
            (semi_y * math.cos(angle)) ** 2
            + (semi_x * math.sin(angle)) ** 2
        )
        factors.append((semi_x * semi_y / denominator) / radius_m)
    return GeometryProfile(
        profile_id=profile_id,
        display_name=display_name,
        radius_m=radius_m,
        boundary_radius_factors=tuple(factors),
        shape_kind="ellipse",
        width_m=width_m,
        height_m=height_m,
        rotation_degrees=rotation_degrees,
        lungs_enabled=lungs_enabled,
        left_lung_radius_factors=left_lung_radius_factors,
        right_lung_radius_factors=right_lung_radius_factors,
        left_lung_center=left_lung_center,
        right_lung_center=right_lung_center,
    )


_PROFILES = {
    "adult": GeometryProfile(
        profile_id="adult-circle-v1",
        display_name="Взрослый — круглая модель",
        radius_m=0.15,
    ),
    "infant": GeometryProfile(
        profile_id="infant-circle-v1",
        display_name="Младенец — круглая модель",
        radius_m=0.08,
    ),
    "adult_ellipse": ellipse_profile(
        width_m=0.30,
        height_m=0.24,
        profile_id="adult-ellipse-v1",
        display_name="Взрослый — эллипс 300×240 мм",
    ),
    "infant_ellipse": ellipse_profile(
        width_m=0.16,
        height_m=0.13,
        profile_id="infant-ellipse-v1",
        display_name="Младенец — эллипс 160×130 мм",
    ),
}


def geometry_profile(name: str) -> GeometryProfile:
    """Вернуть встроенный профиль геометрии по стабильному имени или id."""

    if name in _PROFILES:
        return _PROFILES[name]
    for profile in _PROFILES.values():
        if profile.profile_id == name:
            return profile
    choices = ", ".join(sorted(_PROFILES))
    raise ValueError(f"Неизвестный профиль геометрии {name!r}; доступны: {choices}")


def builtin_geometry_profiles() -> tuple[GeometryProfile, ...]:
    """Profiles shown in the engineering section library, without aliases."""

    return tuple(_PROFILES[name] for name in (
        "adult_ellipse", "adult", "infant_ellipse", "infant"
    ))

