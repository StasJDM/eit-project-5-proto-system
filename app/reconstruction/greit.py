"""Обучаемая линейная реконструкция GREIT на фиксированной пиксельной сетке."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import math
from numbers import Integral, Real
from threading import RLock
from typing import Callable

import numpy as np

from .forward import CompleteElectrodeModel
from .reconstruction import (
    MapConvention,
    ReconstructionCancelledError,
    ReconstructionError,
)


_GREIT_MATRIX_VERSION = "greit-linearized-local-targets-v1"


@dataclass(frozen=True)
class GreitConfig:
    """Воспроизводимые параметры построения линейного оператора GREIT.

    Матрица обучается на локальных гауссовых изменениях проводимости. Базовый
    ``regularization_lambda`` задаёт нижнюю границу относительной
    регуляризации Тихонова. Если указан ``noise_figure``, дополнительная
    регуляризация подбирается так, чтобы приблизиться к целевому NF, но не
    ослабляет эту границу.
    """

    regularization_lambda: float = 0.02
    noise_figure: float | None = 0.5
    pixel_size: int = 64
    training_target_radius_fraction: float = 0.12
    desired_resolution_fraction: float = 0.18
    training_amplitude_s_m: float = 0.10
    maximum_training_radius_fraction: float = 0.78
    svd_rcond: float = 1e-10
    current_amperes: float = 1.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.pixel_size, bool)
            or not isinstance(self.pixel_size, Integral)
            or self.pixel_size < 4
        ):
            raise ValueError("Размер пиксельной карты должен быть не меньше 4")
        positive = (
            ("Коэффициент регуляризации", self.regularization_lambda),
            ("Радиус обучающего возмущения", self.training_target_radius_fraction),
            ("Целевое разрешение", self.desired_resolution_fraction),
            ("Амплитуда обучающего возмущения", self.training_amplitude_s_m),
            ("Максимальный радиус обучающих центров", self.maximum_training_radius_fraction),
            ("Порог сингулярных чисел", self.svd_rcond),
            ("Амплитуда тока", self.current_amperes),
        )
        for label, value in positive:
            if (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{label} должен быть положительным конечным числом")
        if self.noise_figure is not None and (
            isinstance(self.noise_figure, bool)
            or not isinstance(self.noise_figure, Real)
            or not math.isfinite(self.noise_figure)
            or self.noise_figure <= 0
        ):
            raise ValueError("Noise figure должен быть положительным конечным числом")
        if self.training_target_radius_fraction >= 0.5:
            raise ValueError("Радиус обучающего возмущения должен быть меньше 0,5 радиуса")
        if self.desired_resolution_fraction >= 0.5:
            raise ValueError("Целевое разрешение должно быть меньше 0,5 радиуса")
        if not 0 < self.maximum_training_radius_fraction < 1:
            raise ValueError("Центры обучения должны находиться внутри контура")


@dataclass(frozen=True)
class GreitMatrixDiagnostics:
    training_target_count: int
    effective_rank: int
    regularization_relative: float
    regularization_absolute: float
    target_noise_figure: float | None
    achieved_noise_figure: float
    active_channel_count: int


@dataclass(frozen=True)
class GreitReconstructionMatrix:
    """Неизменяемый оператор из сырых ``Delta V`` в пиксели ``Delta sigma``."""

    reconstruction_matrix: np.ndarray
    inside_mask: np.ndarray
    training_centers: np.ndarray
    diagnostics: GreitMatrixDiagnostics
    compatibility_key: tuple


@dataclass(frozen=True)
class GreitResult:
    image: np.ndarray
    active_channel_count: int
    convention: MapConvention
    validated_for_real_data: bool
    matrix_diagnostics: GreitMatrixDiagnostics

    @property
    def iteration_count(self) -> int:
        """GREIT применяет готовую матрицу и не выполняет итераций на кадре."""

        return 0

    @property
    def stop_reason(self) -> str:
        nf = self.matrix_diagnostics.achieved_noise_figure
        return f"линейный оператор GREIT, NF={nf:.3g}"


class GreitMatrixCache:
    """Ограниченный потокобезопасный LRU-кэш обученных матриц GREIT."""

    def __init__(self, max_entries: int = 8) -> None:
        if max_entries < 1:
            raise ValueError("Кэш должен вмещать хотя бы одну матрицу GREIT")
        self.max_entries = int(max_entries)
        self._entries: OrderedDict[tuple, GreitReconstructionMatrix] = OrderedDict()
        self._lock = RLock()

    def get_or_build(
        self,
        key: tuple,
        builder: Callable[[], GreitReconstructionMatrix],
    ) -> tuple[GreitReconstructionMatrix, bool]:
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                return cached, True
            matrix = builder()
            if matrix.compatibility_key != key:
                raise ReconstructionError("Матрица GREIT построена с несовместимым ключом")
            self._entries[key] = matrix
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
            return matrix, False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


_DEFAULT_GREIT_MATRIX_CACHE = GreitMatrixCache()


def get_default_greit_matrix_cache() -> GreitMatrixCache:
    return _DEFAULT_GREIT_MATRIX_CACHE


class GreitReconstructor:
    """Построить и применить GREIT-оператор для конкретной КЭ-модели."""

    def __init__(
        self,
        model: CompleteElectrodeModel,
        config: GreitConfig | None = None,
        *,
        matrix_cache: GreitMatrixCache | None = None,
    ) -> None:
        self.model = model
        self.config = config or GreitConfig()
        self.matrix_cache = matrix_cache or get_default_greit_matrix_cache()

    def reconstruct(
        self,
        delta_measurements: np.ndarray,
        *,
        reference_conductivity: float | np.ndarray | None = None,
        channel_weights: np.ndarray | None = None,
        progress_callback: Callable[[str, float], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> GreitResult:
        self._raise_if_cancelled(cancel_check)
        delta_v = self._measurement_vector(delta_measurements)
        weights = self._channel_weights(channel_weights)
        reference = self._reference_vector(reference_conductivity)
        matrix, from_cache = self.prepare_matrix(
            reference_conductivity=reference,
            channel_weights=weights,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        self._raise_if_cancelled(cancel_check)
        if progress_callback is not None:
            progress_callback(
                "GREIT: применение матрицы из кэша"
                if from_cache
                else "GREIT: применение обученной матрицы",
                0.96,
            )
        flat = matrix.reconstruction_matrix @ delta_v
        if not np.isfinite(flat).all():
            raise ReconstructionError("Результат GREIT содержит нечисловые значения")
        image = flat.reshape(self.config.pixel_size, self.config.pixel_size).copy()
        image[~matrix.inside_mask] = np.nan
        image.setflags(write=False)
        convention = MapConvention(
            electrode_orientation_confirmed=self.model.protocol.electrode_order_confirmed
        )
        return GreitResult(
            image=image,
            active_channel_count=int(np.count_nonzero(weights)),
            convention=convention,
            validated_for_real_data=self.model.validated_for_real_data,
            matrix_diagnostics=matrix.diagnostics,
        )

    def prepare_matrix(
        self,
        *,
        reference_conductivity: float | np.ndarray | None = None,
        channel_weights: np.ndarray | None = None,
        progress_callback: Callable[[str, float], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> tuple[GreitReconstructionMatrix, bool]:
        reference = self._reference_vector(reference_conductivity)
        weights = self._channel_weights(channel_weights)
        key = self._compatibility_key(reference, weights)

        def build() -> GreitReconstructionMatrix:
            return self._build_matrix(
                key,
                reference,
                weights,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )

        return self.matrix_cache.get_or_build(key, build)

    def _build_matrix(
        self,
        compatibility_key: tuple,
        reference: np.ndarray,
        weights: np.ndarray,
        *,
        progress_callback: Callable[[str, float], None] | None,
        cancel_check: Callable[[], bool] | None,
    ) -> GreitReconstructionMatrix:
        self._progress(progress_callback, "GREIT: обучающие возмущения", 0.22)
        centers = self._training_centers()
        element_targets = self._element_targets(centers)
        inside_mask, desired = self._desired_images(centers, element_targets)
        self._raise_if_cancelled(cancel_check)

        self._progress(progress_callback, "GREIT: матрица чувствительности", 0.43)
        jacobian = self.model.jacobian(
            reference, current_amperes=self.config.current_amperes
        )
        training_measurements = jacobian @ element_targets
        sqrt_weights = np.sqrt(weights)
        weighted_measurements = sqrt_weights[:, None] * training_measurements
        self._raise_if_cancelled(cancel_check)

        self._progress(progress_callback, "GREIT: регуляризованное обучение", 0.66)
        try:
            left, singular_values, right_t = np.linalg.svd(
                weighted_measurements, full_matrices=False
            )
        except np.linalg.LinAlgError as exc:
            raise ReconstructionError("SVD обучающих данных GREIT не сошлось") from exc
        if singular_values.size == 0 or not np.isfinite(singular_values).all():
            raise ReconstructionError("Обучающие данные GREIT имеют неверный спектр")
        largest = float(singular_values[0])
        active = singular_values > self.config.svd_rcond * largest
        rank = int(np.count_nonzero(active))
        if rank == 0 or largest <= np.finfo(float).tiny:
            raise ReconstructionError("Обучающие данные GREIT не имеют чувствительности")

        desired_basis = desired @ right_t.T
        central_signal = weighted_measurements[:, 0]
        relative_lambda, achieved_nf = self._select_regularization(
            desired_basis,
            left,
            singular_values,
            active,
            central_signal,
            weights > 0,
            inside_mask.ravel(),
        )
        regularization = relative_lambda * largest
        filters = np.zeros_like(singular_values)
        filters[active] = singular_values[active] / (
            singular_values[active] ** 2 + regularization**2
        )
        weighted_operator = (desired_basis * filters) @ left.T
        reconstruction_matrix = weighted_operator * sqrt_weights[None, :]
        reconstruction_matrix[~inside_mask.ravel(), :] = 0.0
        if not np.isfinite(reconstruction_matrix).all():
            raise ReconstructionError("Матрица GREIT содержит нечисловые значения")
        self._raise_if_cancelled(cancel_check)
        self._progress(progress_callback, "GREIT: матрица сохранена в кэше", 0.90)

        diagnostics = GreitMatrixDiagnostics(
            training_target_count=centers.shape[0],
            effective_rank=rank,
            regularization_relative=relative_lambda,
            regularization_absolute=regularization,
            target_noise_figure=self.config.noise_figure,
            achieved_noise_figure=achieved_nf,
            active_channel_count=int(np.count_nonzero(weights)),
        )
        for array in (reconstruction_matrix, inside_mask, centers):
            array.setflags(write=False)
        return GreitReconstructionMatrix(
            reconstruction_matrix=reconstruction_matrix,
            inside_mask=inside_mask,
            training_centers=centers,
            diagnostics=diagnostics,
            compatibility_key=compatibility_key,
        )

    def _select_regularization(
        self,
        desired_basis: np.ndarray,
        left: np.ndarray,
        singular_values: np.ndarray,
        active: np.ndarray,
        central_signal: np.ndarray,
        active_channels: np.ndarray,
        inside: np.ndarray,
    ) -> tuple[float, float]:
        base = self.config.regularization_lambda
        if self.config.noise_figure is None:
            return base, self._noise_figure_for_lambda(
                base,
                desired_basis,
                left,
                singular_values,
                active,
                central_signal,
                active_channels,
                inside,
            )

        # NF может быть немонотонным при чрезмерной регуляризации. Ищется
        # ближайшая цель на ветви от заданной нижней границы; при равенстве
        # выбирается меньшая регуляризация и, следовательно, лучшее разрешение.
        candidates = np.unique(
            np.concatenate(
                (
                    np.array((base,), dtype=float),
                    np.logspace(
                        math.log10(base),
                        math.log10(max(1000.0, base)),
                        181,
                    ),
                )
            )
        )
        target = self.config.noise_figure
        values = np.array(
            [
                self._noise_figure_for_lambda(
                    value,
                    desired_basis,
                    left,
                    singular_values,
                    active,
                    central_signal,
                    active_channels,
                    inside,
                )
                for value in candidates
            ]
        )
        error = np.abs(values - target)
        best = int(np.flatnonzero(error == np.min(error))[0])
        return float(candidates[best]), float(values[best])

    @staticmethod
    def _noise_figure_for_lambda(
        relative_lambda: float,
        desired_basis: np.ndarray,
        left: np.ndarray,
        singular_values: np.ndarray,
        active: np.ndarray,
        central_signal: np.ndarray,
        active_channels: np.ndarray,
        inside: np.ndarray,
    ) -> float:
        regularization = relative_lambda * float(singular_values[0])
        filters = np.zeros_like(singular_values)
        filters[active] = singular_values[active] / (
            singular_values[active] ** 2 + regularization**2
        )
        coefficient = filters * (left.T @ central_signal)
        image_signal = desired_basis @ coefficient
        # U ортонормальна, поэтому норма строки оператора равна норме
        # соответствующей строки desired_basis * filters.
        image_noise = np.linalg.norm(desired_basis * filters, axis=1)
        mean_image_signal = float(np.mean(np.abs(image_signal[inside])))
        if mean_image_signal <= np.finfo(float).tiny:
            return float("inf")
        data_signal = float(np.mean(np.abs(central_signal[active_channels])))
        data_noise = 1.0
        output_noise = float(np.mean(image_noise[inside]))
        return (data_signal / data_noise) / (mean_image_signal / output_noise)

    def _training_centers(self) -> np.ndarray:
        maximum = self.config.maximum_training_radius_fraction
        centers: list[tuple[float, float]] = [(0.0, 0.0)]
        rings = (
            (maximum * 0.20 / 0.78, 6),
            (maximum * 0.40 / 0.78, 12),
            (maximum * 0.60 / 0.78, 18),
            (maximum, 24),
        )
        for ring_index, (fraction, count) in enumerate(rings):
            offset = 0.5 if ring_index % 2 else 0.0
            for index in range(count):
                angle = 2.0 * math.pi * (index + offset) / count
                boundary = self.model.profile.radius_at(angle)
                local_radius = fraction * boundary
                centers.append(
                    (local_radius * math.cos(angle), local_radius * math.sin(angle))
                )
        return np.asarray(centers, dtype=float)

    def _element_targets(self, centers: np.ndarray) -> np.ndarray:
        centroids = self.model.mesh.nodes[self.model.mesh.elements].mean(axis=1)
        width = (
            self.config.training_target_radius_fraction * self.model.profile.radius_m
        )
        distance_squared = np.sum(
            (centroids[:, None, :] - centers[None, :, :]) ** 2, axis=2
        )
        return self.config.training_amplitude_s_m * np.exp(
            -distance_squared / (2.0 * width**2)
        )

    def _desired_images(
        self, centers: np.ndarray, element_targets: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        size = self.config.pixel_size
        extent = float(np.max(np.abs(self.model.mesh.nodes)))
        axis = np.linspace(-extent, extent, size)
        xx, yy = np.meshgrid(axis, axis[::-1])
        pixels = np.column_stack((xx.ravel(), yy.ravel()))
        inside = np.isfinite(
            self.model.element_values_to_pixels(
                np.ones(self.model.mesh.element_count), size=size
            )
        ).ravel()
        width = self.config.desired_resolution_fraction * self.model.profile.radius_m
        distance_squared = np.sum(
            (pixels[:, None, :] - centers[None, :, :]) ** 2, axis=2
        )
        desired = np.exp(-distance_squared / (2.0 * width**2))
        desired[~inside, :] = 0.0
        for index in range(centers.shape[0]):
            projected = self.model.element_values_to_pixels(
                element_targets[:, index], size=size
            )
            target_sum = float(np.nansum(projected))
            desired_sum = float(np.sum(desired[:, index]))
            if desired_sum <= np.finfo(float).tiny:
                raise ReconstructionError("Целевой образ GREIT не попал в пиксельную сетку")
            desired[:, index] *= target_sum / desired_sum
        return inside.reshape(size, size), desired

    def _compatibility_key(self, reference: np.ndarray, weights: np.ndarray) -> tuple:
        return (
            _GREIT_MATRIX_VERSION,
            self.model.profile.cache_key(),
            self.model.protocol,
            self.model.mesh.density.value,
            tuple(float(value) for value in self.model.contact_impedances),
            hashlib.sha256(reference.tobytes()).hexdigest(),
            hashlib.sha256(weights.tobytes()).hexdigest(),
            self.config,
        )

    def _measurement_vector(self, values: np.ndarray) -> np.ndarray:
        vector = np.asarray(values, dtype=float)
        expected = self.model.protocol.expected_channel_count
        if vector.shape != (expected,):
            raise ValueError(f"Разность измерений должна иметь форму ({expected},)")
        if not np.isfinite(vector).all():
            raise ValueError("Разность измерений должна содержать только конечные числа")
        return np.ascontiguousarray(vector)

    def _channel_weights(self, values: np.ndarray | None) -> np.ndarray:
        expected = self.model.protocol.expected_channel_count
        weights = (
            np.ones(expected, dtype=float)
            if values is None
            else np.asarray(values, dtype=float)
        )
        if weights.shape != (expected,):
            raise ValueError(f"Веса каналов должны иметь форму ({expected},)")
        if not np.isfinite(weights).all() or np.any(weights < 0):
            raise ValueError("Веса каналов должны быть неотрицательными и конечными")
        if not np.any(weights > 0):
            raise ValueError("Хотя бы один канал должен иметь ненулевой вес")
        return np.ascontiguousarray(weights)

    def _reference_vector(self, conductivity: float | np.ndarray | None) -> np.ndarray:
        value = (
            self.model.profile.background_conductivity_s_m
            if conductivity is None
            else conductivity
        )
        return self.model.conductivity_vector(value)

    @staticmethod
    def _raise_if_cancelled(cancel_check: Callable[[], bool] | None) -> None:
        if cancel_check is not None and cancel_check():
            raise ReconstructionCancelledError("Реконструкция отменена")

    @staticmethod
    def _progress(
        callback: Callable[[str, float], None] | None,
        message: str,
        fraction: float,
    ) -> None:
        if callback is not None:
            callback(message, fraction)

