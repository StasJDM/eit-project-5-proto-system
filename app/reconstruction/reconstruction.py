"""Регуляризованная абсолютная и разностная реконструкция Гаусса—Ньютона."""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Integral
from typing import Callable

import numpy as np

from .forward import CompleteElectrodeModel


class ReconstructionError(RuntimeError):
    """Диагностируемая ошибка вычислительной реконструкции."""


class ReconstructionCancelledError(ReconstructionError):
    """Расчёт штатно отменён вызывающей стороной."""


@dataclass(frozen=True)
class GaussNewtonConfig:
    """Явные и воспроизводимые настройки итерационной реконструкции.

    ``regularization_lambda`` является относительным коэффициентом: на каждой
    итерации абсолютный параметр Тихонова равен ``lambda * s_max`` для
    взвешенного якобиана. Это делает настройку независимее от амплитуды тока.
    """

    max_iterations: int = 8
    regularization_lambda: float = 0.01
    residual_tolerance: float = 1e-3
    update_tolerance: float = 1e-4
    svd_rcond: float = 1e-10
    min_conductivity_s_m: float = 0.05
    max_conductivity_s_m: float = 5.0
    initial_step: float = 1.0
    min_step: float = 1.0 / 64.0
    pixel_size: int = 64
    current_amperes: float = 1.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_iterations, bool)
            or not isinstance(self.max_iterations, Integral)
            or self.max_iterations < 1
        ):
            raise ValueError("Число итераций должно быть положительным целым")
        if (
            isinstance(self.pixel_size, bool)
            or not isinstance(self.pixel_size, Integral)
            or self.pixel_size < 4
        ):
            raise ValueError("Размер пиксельной карты должен быть не меньше 4")
        positive_values = (
            ("Коэффициент регуляризации", self.regularization_lambda),
            ("Порог невязки", self.residual_tolerance),
            ("Порог обновления", self.update_tolerance),
            ("Порог сингулярных чисел", self.svd_rcond),
            ("Минимальная проводимость", self.min_conductivity_s_m),
            ("Максимальная проводимость", self.max_conductivity_s_m),
            ("Начальный шаг", self.initial_step),
            ("Минимальный шаг", self.min_step),
            ("Амплитуда тока", self.current_amperes),
        )
        for label, value in positive_values:
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{label} должен быть положительным конечным числом")
        if self.min_conductivity_s_m >= self.max_conductivity_s_m:
            raise ValueError("Минимальная проводимость должна быть меньше максимальной")
        if self.initial_step > 1:
            raise ValueError("Начальный шаг не должен превышать 1")
        if self.min_step > self.initial_step:
            raise ValueError("Минимальный шаг не должен превышать начальный")


@dataclass(frozen=True)
class MapConvention:
    quantity: str = "изменение проводимости Δσ"
    units: str = "См/м в эффективной 2D-модели"
    positive_sign: str = "положительное значение означает рост проводимости"
    horizontal_axis: str = "+x направлен к номинальному электроду 1"
    vertical_axis: str = "+y направлен к росту угла электродов; верх карты = +y"
    anatomical_labels: str = "анатомические лево/право и перед/зад не назначены"
    electrode_orientation_confirmed: bool = False


@dataclass(frozen=True)
class IterationDiagnostic:
    iteration: int
    weighted_residual_norm: float
    relative_residual: float
    relative_update: float
    step_size: float
    effective_rank: int
    condition_number: float
    regularization_absolute: float
    clipped_elements: int


@dataclass(frozen=True)
class GaussNewtonResult:
    reference_conductivity: np.ndarray
    conductivity: np.ndarray
    delta_conductivity: np.ndarray
    image: np.ndarray
    predicted_delta_measurements: np.ndarray
    residual_measurements: np.ndarray
    diagnostics: tuple[IterationDiagnostic, ...]
    converged: bool
    stop_reason: str
    active_channel_count: int
    convention: MapConvention
    validated_for_real_data: bool
    reconstruction_mode: str

    @property
    def iteration_count(self) -> int:
        return len(self.diagnostics)


class GaussNewtonReconstructor:
    """Итерационная нелинейная реконструкция на КЭ-сетке."""

    def __init__(
        self,
        model: CompleteElectrodeModel,
        config: GaussNewtonConfig | None = None,
    ) -> None:
        self.model = model
        self.config = config or GaussNewtonConfig()

    def reconstruct(
        self,
        delta_measurements: np.ndarray,
        *,
        reference_conductivity: float | np.ndarray | None = None,
        channel_weights: np.ndarray | None = None,
        progress_callback: Callable[[IterationDiagnostic], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> GaussNewtonResult:
        """Восстановить ``Δσ`` из абсолютной разности измерений ``ΔV``.

        Веса трактуются как надёжность каналов: нулевой вес исключает канал,
        а в целевой функции используется ``sqrt(weight)``.
        """

        self._raise_if_cancelled(cancel_check)
        delta_v = self._measurement_vector(
            delta_measurements, label="Разность измерений"
        )
        weights = self._channel_weights(channel_weights)
        reference_sigma = self._reference_vector(reference_conductivity)
        reference_forward = self.model.solve(
            reference_sigma, current_amperes=self.config.current_amperes
        ).measurements
        self._raise_if_cancelled(cancel_check)
        target_measurements = reference_forward + delta_v
        return self._solve_target(
            target_measurements,
            reference_sigma=reference_sigma,
            reference_forward=reference_forward,
            weights=weights,
            reconstruction_mode="difference",
            zero_stop_reason="нулевая разность измерений",
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    def reconstruct_absolute(
        self,
        measurements: np.ndarray,
        *,
        prior_conductivity: float | np.ndarray | None = None,
        channel_weights: np.ndarray | None = None,
        progress_callback: Callable[[IterationDiagnostic], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> GaussNewtonResult:
        """Восстановить абсолютную ``sigma`` одного кадра без измерительной опоры.

        ``prior_conductivity`` задаёт априорную однородную или пространственную
        модель и начальную точку. В отличие от разностного режима, регуляризация
        удерживает само решение около prior, а не только уменьшает текущий шаг.
        Каждый вызов начинает итерации заново и не использует соседние кадры.
        """

        self._raise_if_cancelled(cancel_check)
        target_measurements = self._measurement_vector(
            measurements, label="Абсолютные измерения"
        )
        weights = self._channel_weights(channel_weights)
        prior_sigma = self._reference_vector(prior_conductivity)
        prior_forward = self.model.solve(
            prior_sigma, current_amperes=self.config.current_amperes
        ).measurements
        self._raise_if_cancelled(cancel_check)
        return self._solve_target(
            target_measurements,
            reference_sigma=prior_sigma,
            reference_forward=prior_forward,
            weights=weights,
            reconstruction_mode="absolute",
            zero_stop_reason="измерения совпадают с априорной моделью",
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    def _solve_target(
        self,
        target_measurements: np.ndarray,
        *,
        reference_sigma: np.ndarray,
        reference_forward: np.ndarray,
        weights: np.ndarray,
        reconstruction_mode: str,
        zero_stop_reason: str,
        progress_callback: Callable[[IterationDiagnostic], None] | None,
        cancel_check: Callable[[], bool] | None,
    ) -> GaussNewtonResult:
        """Решить общую нелинейную задачу для абсолютного целевого вектора."""

        absolute = reconstruction_mode == "absolute"
        sqrt_weights = np.sqrt(weights)
        active_channel_count = int(np.count_nonzero(weights))
        data_delta = target_measurements - reference_forward
        data_norm = float(np.linalg.norm(sqrt_weights * data_delta))
        numerical_scale = np.finfo(float).eps * max(
            1.0, float(np.linalg.norm(sqrt_weights * reference_forward))
        )
        if data_norm <= numerical_scale:
            return self._result(
                reference_sigma,
                reference_sigma.copy(),
                np.zeros_like(reference_forward),
                data_delta.copy(),
                (),
                converged=True,
                stop_reason=zero_stop_reason,
                active_channel_count=active_channel_count,
                reconstruction_mode=reconstruction_mode,
            )

        sigma = reference_sigma.copy()
        diagnostics: list[IterationDiagnostic] = []
        converged = False
        stop_reason = "достигнут предел итераций"

        predicted = reference_forward
        residual = target_measurements - predicted
        for iteration in range(1, self.config.max_iterations + 1):
            self._raise_if_cancelled(cancel_check)
            residual_norm = float(np.linalg.norm(sqrt_weights * residual))
            relative_residual = residual_norm / data_norm
            if relative_residual <= self.config.residual_tolerance:
                converged = True
                stop_reason = "достигнут порог относительной невязки"
                break

            jacobian = self.model.jacobian(
                sigma, current_amperes=self.config.current_amperes
            )
            self._raise_if_cancelled(cancel_check)
            weighted_jacobian = sqrt_weights[:, None] * jacobian
            weighted_residual = sqrt_weights * residual
            if absolute:
                prior_offset = sigma - reference_sigma
                regularized_solution, rank, condition, regularization = (
                    self._regularized_update(
                        weighted_jacobian,
                        weighted_residual + weighted_jacobian @ prior_offset,
                    )
                )
                update = regularized_solution - prior_offset
            else:
                update, rank, condition, regularization = self._regularized_update(
                    weighted_jacobian, weighted_residual
                )

            accepted = False
            current_objective = residual_norm**2
            if absolute:
                current_objective += regularization**2 * float(
                    np.linalg.norm(sigma - reference_sigma) ** 2
                )
            step = self.config.initial_step
            candidate_sigma = sigma
            candidate_predicted = predicted
            candidate_residual = residual
            clipped_elements = 0
            while step + np.finfo(float).eps >= self.config.min_step:
                self._raise_if_cancelled(cancel_check)
                unconstrained = sigma + step * update
                trial_sigma = np.clip(
                    unconstrained,
                    self.config.min_conductivity_s_m,
                    self.config.max_conductivity_s_m,
                )
                clipped = int(np.count_nonzero(trial_sigma != unconstrained))
                if np.array_equal(trial_sigma, sigma):
                    step *= 0.5
                    continue
                trial_predicted = self.model.solve(
                    trial_sigma, current_amperes=self.config.current_amperes
                ).measurements
                self._raise_if_cancelled(cancel_check)
                trial_residual = target_measurements - trial_predicted
                trial_norm = float(np.linalg.norm(sqrt_weights * trial_residual))
                trial_objective = trial_norm**2
                if absolute:
                    trial_objective += regularization**2 * float(
                        np.linalg.norm(trial_sigma - reference_sigma) ** 2
                    )
                if trial_objective < current_objective:
                    accepted = True
                    candidate_sigma = trial_sigma
                    candidate_predicted = trial_predicted
                    candidate_residual = trial_residual
                    clipped_elements = clipped
                    break
                step *= 0.5

            if not accepted:
                diagnostic = IterationDiagnostic(
                    iteration=iteration,
                    weighted_residual_norm=residual_norm,
                    relative_residual=relative_residual,
                    relative_update=0.0,
                    step_size=0.0,
                    effective_rank=rank,
                    condition_number=condition,
                    regularization_absolute=regularization,
                    clipped_elements=0,
                )
                diagnostics.append(diagnostic)
                if progress_callback is not None:
                    progress_callback(diagnostic)
                stop_reason = (
                    "линейный поиск не уменьшил целевую функцию"
                    if absolute
                    else "линейный поиск не уменьшил невязку"
                )
                break

            relative_update = float(
                np.linalg.norm(candidate_sigma - sigma)
                / max(np.linalg.norm(sigma), np.finfo(float).eps)
            )
            sigma = candidate_sigma
            predicted = candidate_predicted
            residual = candidate_residual
            new_residual_norm = float(np.linalg.norm(sqrt_weights * residual))
            diagnostic = IterationDiagnostic(
                iteration=iteration,
                weighted_residual_norm=new_residual_norm,
                relative_residual=new_residual_norm / data_norm,
                relative_update=relative_update,
                step_size=step,
                effective_rank=rank,
                condition_number=condition,
                regularization_absolute=regularization,
                clipped_elements=clipped_elements,
            )
            diagnostics.append(diagnostic)
            if progress_callback is not None:
                progress_callback(diagnostic)

            if diagnostic.relative_residual <= self.config.residual_tolerance:
                converged = True
                stop_reason = "достигнут порог относительной невязки"
                break
            if relative_update <= self.config.update_tolerance:
                converged = True
                stop_reason = "достигнут порог относительного обновления"
                break

        self._raise_if_cancelled(cancel_check)
        predicted_delta = predicted - reference_forward
        return self._result(
            reference_sigma,
            sigma,
            predicted_delta,
            residual,
            tuple(diagnostics),
            converged=converged,
            stop_reason=stop_reason,
            active_channel_count=active_channel_count,
            reconstruction_mode=reconstruction_mode,
        )

    @staticmethod
    def _raise_if_cancelled(cancel_check: Callable[[], bool] | None) -> None:
        if cancel_check is not None and cancel_check():
            raise ReconstructionCancelledError("Реконструкция отменена")

    def _measurement_vector(self, values: np.ndarray, *, label: str) -> np.ndarray:
        vector = np.asarray(values, dtype=float)
        expected = self.model.protocol.expected_channel_count
        if vector.shape != (expected,):
            raise ValueError(f"{label} должны иметь форму ({expected},)")
        if not np.isfinite(vector).all():
            raise ValueError(f"{label} должны содержать только конечные числа")
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
        vector = self.model.conductivity_vector(value)
        if np.any(vector < self.config.min_conductivity_s_m) or np.any(
            vector > self.config.max_conductivity_s_m
        ):
            raise ValueError("Опорная проводимость находится вне заданных ограничений")
        return vector

    def _regularized_update(
        self, weighted_jacobian: np.ndarray, weighted_residual: np.ndarray
    ) -> tuple[np.ndarray, int, float, float]:
        try:
            left, singular_values, right_t = np.linalg.svd(
                weighted_jacobian, full_matrices=False
            )
        except np.linalg.LinAlgError as exc:
            raise ReconstructionError(
                "SVD якобиана не сошлось; реконструкция остановлена"
            ) from exc
        if singular_values.size == 0 or not np.isfinite(singular_values).all():
            raise ReconstructionError("Не удалось получить конечные сингулярные числа")
        largest = float(singular_values[0])
        threshold = self.config.svd_rcond * largest
        active = singular_values > threshold
        rank = int(np.count_nonzero(active))
        if rank == 0 or largest <= np.finfo(float).tiny:
            raise ReconstructionError("Якобиан имеет нулевую численную чувствительность")
        smallest_active = float(singular_values[active][-1])
        condition = largest / smallest_active
        regularization = self.config.regularization_lambda * largest
        filters = np.zeros_like(singular_values)
        filters[active] = singular_values[active] / (
            singular_values[active] ** 2 + regularization**2
        )
        update = right_t.T @ (filters * (left.T @ weighted_residual))
        if not np.isfinite(update).all():
            raise ReconstructionError("Регуляризованное обновление содержит нечисловые значения")
        return update, rank, condition, regularization

    def _result(
        self,
        reference_sigma: np.ndarray,
        sigma: np.ndarray,
        predicted_delta: np.ndarray,
        residual: np.ndarray,
        diagnostics: tuple[IterationDiagnostic, ...],
        *,
        converged: bool,
        stop_reason: str,
        active_channel_count: int,
        reconstruction_mode: str,
    ) -> GaussNewtonResult:
        delta_sigma = sigma - reference_sigma
        image_values = sigma if reconstruction_mode == "absolute" else delta_sigma
        image = self.model.element_values_to_pixels(
            image_values, size=self.config.pixel_size
        )
        convention = (
            MapConvention(
                quantity="абсолютная проводимость σ",
                units="См/м в эффективной 2D-модели",
                positive_sign="большее значение означает большую проводимость",
                electrode_orientation_confirmed=(
                    self.model.protocol.electrode_order_confirmed
                ),
            )
            if reconstruction_mode == "absolute"
            else MapConvention(
                electrode_orientation_confirmed=(
                    self.model.protocol.electrode_order_confirmed
                )
            )
        )
        arrays = (
            reference_sigma.copy(),
            sigma.copy(),
            delta_sigma.copy(),
            image.copy(),
            predicted_delta.copy(),
            residual.copy(),
        )
        for array in arrays:
            array.setflags(write=False)
        return GaussNewtonResult(
            reference_conductivity=arrays[0],
            conductivity=arrays[1],
            delta_conductivity=arrays[2],
            image=arrays[3],
            predicted_delta_measurements=arrays[4],
            residual_measurements=arrays[5],
            diagnostics=diagnostics,
            converged=converged,
            stop_reason=stop_reason,
            active_channel_count=active_channel_count,
            convention=convention,
            validated_for_real_data=self.model.validated_for_real_data,
            reconstruction_mode=reconstruction_mode,
        )

