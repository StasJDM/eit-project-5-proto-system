"""Описание измерительного протокола и порядка каналов ЭИТ."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping


class ProtocolDefinitionError(ValueError):
    """Внешнее описание протокола неполно или противоречиво."""


@dataclass(frozen=True)
class ElectrodeDefinition:
    """Номинальное положение электрода в выбранном профиле."""

    number: int
    angle_degrees: float
    position_description: str


@dataclass(frozen=True)
class MeasurementChannel:
    """Одно напряжение в сериализованном векторе кадра."""

    index: int
    drive_pair: tuple[int, int]
    measurement_pair: tuple[int, int]
    voltage_definition: str = "phi(first) - phi(second)"
    value_unit: str = "неизвестно"


@dataclass(frozen=True)
class MeasurementProtocol:
    """Самодостаточное описание порядка каналов измерительной системы.

    Встроенный профиль является проверяемой гипотезой для предоставленных
    файлов. Флаг ``channel_order_confirmed`` не позволяет принять эту карту
    каналов за подтверждённый контракт прибора.
    """

    protocol_id: str
    display_name: str
    electrodes: tuple[ElectrodeDefinition, ...]
    channels: tuple[MeasurementChannel, ...]
    drive_pattern: str
    measurement_pattern: str
    excluded_channel_rule: str
    missing_channel_policy: str
    channel_order_description: str
    electrode_order_description: str
    channel_order_confirmed: bool = False
    electrode_order_confirmed: bool = False
    source_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.protocol_id.strip() or not self.display_name.strip():
            raise ProtocolDefinitionError("Идентификатор и название протокола обязательны")
        if not self.electrodes:
            raise ProtocolDefinitionError("Протокол должен содержать электроды")
        numbers = [electrode.number for electrode in self.electrodes]
        if len(set(numbers)) != len(numbers) or any(number < 1 for number in numbers):
            raise ProtocolDefinitionError(
                "Номера электродов должны быть уникальными положительными числами"
            )
        if any(
            not math.isfinite(electrode.angle_degrees)
            for electrode in self.electrodes
        ):
            raise ProtocolDefinitionError("Углы электродов должны быть конечными")
        indices = [channel.index for channel in self.channels]
        if indices != list(range(len(indices))):
            raise ProtocolDefinitionError(
                "Индексы каналов должны быть непрерывны и начинаться с 0"
            )
        valid_numbers = set(numbers)
        for channel in self.channels:
            if len(set(channel.drive_pair)) != 2 or len(set(channel.measurement_pair)) != 2:
                raise ProtocolDefinitionError(
                    f"Канал {channel.index}: каждая пара должна содержать два разных электрода"
                )
            if not set(channel.drive_pair + channel.measurement_pair) <= valid_numbers:
                raise ProtocolDefinitionError(
                    f"Канал {channel.index} ссылается на неизвестный электрод"
                )
        if (self.channel_order_confirmed or self.electrode_order_confirmed) and not (
            self.source_reference and self.source_reference.strip()
        ):
            raise ProtocolDefinitionError(
                "Подтверждённый протокол требует ссылку на первичный источник"
            )

    @property
    def electrode_count(self) -> int:
        return len(self.electrodes)

    @property
    def expected_channel_count(self) -> int:
        return len(self.channels)

    @property
    def status_label(self) -> str:
        return (
            "подтверждён"
            if self.channel_order_confirmed and self.electrode_order_confirmed
            else "гипотеза"
        )

    def channel(self, index: int) -> MeasurementChannel:
        if not 0 <= index < self.expected_channel_count:
            raise IndexError(
                f"Индекс канала {index} вне диапазона "
                f"0..{self.expected_channel_count - 1}"
            )
        return self.channels[index]

    def to_dict(self, include_channels: bool = True) -> dict:
        result = {
            "protocol_id": self.protocol_id,
            "display_name": self.display_name,
            "status": self.status_label,
            "electrode_count": self.electrode_count,
            "expected_channel_count": self.expected_channel_count,
            "drive_pattern": self.drive_pattern,
            "measurement_pattern": self.measurement_pattern,
            "excluded_channel_rule": self.excluded_channel_rule,
            "missing_channel_policy": self.missing_channel_policy,
            "channel_order_description": self.channel_order_description,
            "electrode_order_description": self.electrode_order_description,
            "channel_order_confirmed": self.channel_order_confirmed,
            "electrode_order_confirmed": self.electrode_order_confirmed,
            "source_reference": self.source_reference,
            "electrodes": [asdict(electrode) for electrode in self.electrodes],
        }
        if include_channels:
            result["channels"] = [asdict(channel) for channel in self.channels]
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MeasurementProtocol":
        """Строго прочитать полную таблицу каналов из внешнего профиля."""

        if not isinstance(payload, Mapping):
            raise ProtocolDefinitionError("Раздел protocol должен быть объектом")

        def text(name: str) -> str:
            value = payload.get(name)
            if not isinstance(value, str) or not value.strip():
                raise ProtocolDefinitionError(f"protocol.{name} должен быть непустой строкой")
            return value.strip()

        raw_electrodes = payload.get("electrodes")
        if not isinstance(raw_electrodes, list):
            raise ProtocolDefinitionError("protocol.electrodes должен быть массивом")
        electrodes: list[ElectrodeDefinition] = []
        for index, raw in enumerate(raw_electrodes):
            if not isinstance(raw, Mapping):
                raise ProtocolDefinitionError(
                    f"protocol.electrodes[{index}] должен быть объектом"
                )
            try:
                number = int(raw["number"])
                angle = float(raw["angle_degrees"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ProtocolDefinitionError(
                    f"protocol.electrodes[{index}] требует number и angle_degrees"
                ) from exc
            description = raw.get("position_description")
            if not isinstance(description, str) or not description.strip():
                raise ProtocolDefinitionError(
                    f"protocol.electrodes[{index}].position_description обязателен"
                )
            electrodes.append(ElectrodeDefinition(number, angle, description.strip()))

        raw_channels = payload.get("channels")
        if not isinstance(raw_channels, list):
            raise ProtocolDefinitionError("protocol.channels должен быть массивом")
        channels: list[MeasurementChannel] = []
        for position, raw in enumerate(raw_channels):
            if not isinstance(raw, Mapping):
                raise ProtocolDefinitionError(
                    f"protocol.channels[{position}] должен быть объектом"
                )
            try:
                index = int(raw["index"])
                drive_pair = cls._pair(raw["drive_pair"], position, "drive_pair")
                measurement_pair = cls._pair(
                    raw["measurement_pair"], position, "measurement_pair"
                )
            except (KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, ProtocolDefinitionError):
                    raise
                raise ProtocolDefinitionError(
                    f"protocol.channels[{position}] содержит неверные поля"
                ) from exc
            voltage_definition = raw.get(
                "voltage_definition", "phi(first) - phi(second)"
            )
            value_unit = raw.get("value_unit", "неизвестно")
            if not isinstance(voltage_definition, str) or not voltage_definition.strip():
                raise ProtocolDefinitionError(
                    f"protocol.channels[{position}].voltage_definition обязателен"
                )
            if not isinstance(value_unit, str) or not value_unit.strip():
                raise ProtocolDefinitionError(
                    f"protocol.channels[{position}].value_unit обязателен"
                )
            channels.append(
                MeasurementChannel(
                    index=index,
                    drive_pair=drive_pair,
                    measurement_pair=measurement_pair,
                    voltage_definition=voltage_definition.strip(),
                    value_unit=value_unit.strip(),
                )
            )

        confirmed_channels = payload.get("channel_order_confirmed", False)
        confirmed_electrodes = payload.get("electrode_order_confirmed", False)
        if not isinstance(confirmed_channels, bool) or not isinstance(
            confirmed_electrodes, bool
        ):
            raise ProtocolDefinitionError("Флаги подтверждения protocol должны быть boolean")
        source_reference = payload.get("source_reference")
        if source_reference is not None and (
            not isinstance(source_reference, str) or not source_reference.strip()
        ):
            raise ProtocolDefinitionError(
                "protocol.source_reference должен быть непустой строкой"
            )
        return cls(
            protocol_id=text("protocol_id"),
            display_name=text("display_name"),
            electrodes=tuple(electrodes),
            channels=tuple(channels),
            drive_pattern=text("drive_pattern"),
            measurement_pattern=text("measurement_pattern"),
            excluded_channel_rule=text("excluded_channel_rule"),
            missing_channel_policy=text("missing_channel_policy"),
            channel_order_description=text("channel_order_description"),
            electrode_order_description=text("electrode_order_description"),
            channel_order_confirmed=confirmed_channels,
            electrode_order_confirmed=confirmed_electrodes,
            source_reference=(
                source_reference.strip() if isinstance(source_reference, str) else None
            ),
        )

    @staticmethod
    def _pair(value: Any, channel_index: int, field: str) -> tuple[int, int]:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ProtocolDefinitionError(
                f"protocol.channels[{channel_index}].{field} должен содержать два номера"
            )
        if any(isinstance(item, bool) for item in value):
            raise ProtocolDefinitionError(
                f"protocol.channels[{channel_index}].{field} содержит неверный номер"
            )
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError) as exc:
            raise ProtocolDefinitionError(
                f"protocol.channels[{channel_index}].{field} содержит неверный номер"
            ) from exc

    @classmethod
    def adjacent_16_hypothesis(
        cls,
        *,
        electrode_order: str = "right_ccw",
        measurement_sequence: str = "adjacent_fixed",
    ) -> "MeasurementProtocol":
        """Построить явный, но пока неподтверждённый профиль 16 × 13.

        Индексы формируются группами по токовой паре. Внутри каждой группы
        смежные измерительные пары перебираются от ``(1, 2)`` до ``(16, 1)``;
        три пары, касающиеся токовых электродов, исключаются.
        """

        electrode_count = 16
        electrode_orders = {
            "right_ccw": (0.0, 1.0, "электрод 1 справа, далее против часовой стрелки"),
            "right_cw": (0.0, -1.0, "электрод 1 справа, далее по часовой стрелке"),
            "sternum_cw": (90.0, -1.0, "электрод 1 у грудины, далее по часовой стрелке"),
            "sternum_ccw": (90.0, 1.0, "электрод 1 у грудины, далее против часовой стрелки"),
        }
        if electrode_order not in electrode_orders:
            raise ProtocolDefinitionError(
                f"Неизвестный порядок электродов: {electrode_order!r}"
            )
        start_angle, direction, electrode_description = electrode_orders[electrode_order]
        electrodes = tuple(
            ElectrodeDefinition(
                number=number,
                angle_degrees=(
                    start_angle
                    + direction * (number - 1) * 360.0 / electrode_count
                ) % 360.0,
                position_description=f"номинальная окружность; {electrode_description}",
            )
            for number in range(1, electrode_count + 1)
        )
        adjacent_pairs = tuple(
            (number, number % electrode_count + 1)
            for number in range(1, electrode_count + 1)
        )

        sequence_descriptions = {
            "adjacent_fixed": (
                "токовые пары (1,2)..(16,1); измерительные пары в каждой "
                "группе перебираются в фиксированном порядке (1,2)..(16,1)"
            ),
            "adjacent_rotating": (
                "токовые пары (1,2)..(16,1); начало списка измерительных пар "
                "вращается вместе с токовой парой (EIDORS rotate_meas)"
            ),
            "adjacent_reciprocal": (
                "сначала измерительная пара (1,2)..(16,1), внутри неё "
                "перебираются допустимые токовые пары (взаимный порядок)"
            ),
            "adjacent_reversed": (
                "токовые и измерительные пары перебираются от (16,1) к (1,2)"
            ),
        }
        if measurement_sequence not in sequence_descriptions:
            raise ProtocolDefinitionError(
                f"Неизвестная последовательность измерений: {measurement_sequence!r}"
            )

        pair_rows: list[tuple[tuple[int, int], tuple[int, int]]] = []
        if measurement_sequence == "adjacent_reciprocal":
            for measurement_pair in adjacent_pairs:
                for drive_pair in adjacent_pairs:
                    if not set(drive_pair).intersection(measurement_pair):
                        pair_rows.append((drive_pair, measurement_pair))
        else:
            drive_pairs = (
                tuple(reversed(adjacent_pairs))
                if measurement_sequence == "adjacent_reversed"
                else adjacent_pairs
            )
            for drive_pair in drive_pairs:
                if measurement_sequence == "adjacent_rotating":
                    original_index = adjacent_pairs.index(drive_pair)
                    start = (original_index + 2) % electrode_count
                    measurement_pairs = (
                        adjacent_pairs[start:] + adjacent_pairs[:start]
                    )
                elif measurement_sequence == "adjacent_reversed":
                    measurement_pairs = tuple(reversed(adjacent_pairs))
                else:
                    measurement_pairs = adjacent_pairs
                for measurement_pair in measurement_pairs:
                    if not set(drive_pair).intersection(measurement_pair):
                        pair_rows.append((drive_pair, measurement_pair))

        channels = tuple(
            MeasurementChannel(
                index=index,
                drive_pair=drive_pair,
                measurement_pair=measurement_pair,
            )
            for index, (drive_pair, measurement_pair) in enumerate(pair_rows)
        )

        protocol_id = (
            "adjacent-16x13-hypothesis-v1"
            if electrode_order == "right_ccw"
            and measurement_sequence == "adjacent_fixed"
            else f"adjacent-16x13-{electrode_order}-{measurement_sequence}-hypothesis-v1"
        )

        return cls(
            protocol_id=protocol_id,
            display_name="Смежный 16×13",
            electrodes=electrodes,
            channels=channels,
            drive_pattern="16 смежных токовых пар",
            measurement_pattern="смежные разности phi(first) - phi(second)",
            excluded_channel_rule=(
                "для каждой токовой пары исключаются три смежные пары, "
                "касающиеся токовых электродов"
            ),
            missing_channel_policy=(
                "строгая: пропущенные или дополнительные каналы отклоняются; "
                "восстановление не выполняется"
            ),
            channel_order_description=sequence_descriptions[measurement_sequence],
            electrode_order_description=(
                f"номинально: {electrode_description}; применимость к JSON "
                "не подтверждена"
            ),
        )


DEFAULT_MEASUREMENT_PROTOCOL = MeasurementProtocol.adjacent_16_hypothesis()

