"""Профили геометрии поперечного сечения для 2D-модели ЭИТ."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any, Mapping


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
        )

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
}


def geometry_profile(name: str) -> GeometryProfile:
    """Вернуть встроенный профиль ``adult`` или ``infant``."""

    try:
        return _PROFILES[name]
    except KeyError as exc:
        choices = ", ".join(sorted(_PROFILES))
        raise ValueError(f"Неизвестный профиль геометрии {name!r}; доступны: {choices}") from exc

