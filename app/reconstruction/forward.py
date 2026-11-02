"""Прямая задача ЭИТ на линейных треугольных КЭ с электродной моделью."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import math

import numpy as np

from .geometry import GeometryProfile
from .mesh import FiniteElementMesh
from .protocol import MeasurementProtocol


@dataclass(frozen=True)
class MatrixDimensions:
    node_count: int
    element_count: int
    electrode_count: int
    drive_count: int
    channel_count: int
    system_shape: tuple[int, int]
    jacobian_shape: tuple[int, int]


@dataclass(frozen=True)
class ForwardResult:
    """Результат прямой задачи в порядке каналов протокола."""

    measurements: np.ndarray
    electrode_potentials: np.ndarray
    node_potentials: np.ndarray
    drive_pairs: tuple[tuple[int, int], ...]
    current_amperes: float


@dataclass
class _SolutionBundle:
    system_matrix: np.ndarray
    drive_node_potentials: np.ndarray
    drive_electrode_potentials: np.ndarray
    measurement_adjoint_nodes: np.ndarray


class CompleteElectrodeModel:
    """2D Galerkin FEM для полной электродной модели (CEM).

    На каждом электроде учитываются его конечная ширина, постоянный потенциал
    и эффективный контактный импеданс. Последняя строка системы задаёт
    калибровку ``sum(U)=0``. Модель вещественная и предполагает единичную
    толщину сечения; поэтому она предназначена для синтетической верификации,
    пока единицы и фазовые данные прибора неизвестны.
    """

    def __init__(
        self,
        mesh: FiniteElementMesh,
        profile: GeometryProfile,
        protocol: MeasurementProtocol,
        contact_impedances_ohm_m: float | tuple[float, ...] | None = None,
    ) -> None:
        self.mesh = mesh
        self.profile = profile
        self.protocol = protocol
        if mesh.geometry_profile_id != profile.profile_id:
            raise ValueError("Сетка построена для другого профиля геометрии")
        self._validate_protocol()
        self._electrode_index = {
            electrode.number: index for index, electrode in enumerate(protocol.electrodes)
        }
        self.contact_impedances = self._normalise_contact_impedances(
            contact_impedances_ohm_m
        )
        self.drive_pairs = tuple(dict.fromkeys(channel.drive_pair for channel in protocol.channels))
        self.measurement_pairs = tuple(
            dict.fromkeys(channel.measurement_pair for channel in protocol.channels)
        )
        self._drive_index = {pair: index for index, pair in enumerate(self.drive_pairs)}
        self._measurement_index = {
            pair: index for index, pair in enumerate(self.measurement_pairs)
        }
        self._boundary_matrix = self._assemble_boundary_matrix()
        self._solution_cache: OrderedDict[tuple[str, float], _SolutionBundle] = OrderedDict()
        self._jacobian_cache: OrderedDict[tuple[str, float], np.ndarray] = OrderedDict()
        self._projection_cache: dict[int, np.ndarray] = {}

    def _validate_protocol(self) -> None:
        if self.mesh.electrode_count != self.protocol.electrode_count:
            raise ValueError(
                "Число электродов сетки не совпадает с измерительным протоколом"
            )
        indices = [channel.index for channel in self.protocol.channels]
        if indices != list(range(len(indices))):
            raise ValueError("Индексы каналов протокола должны быть непрерывны от 0")
        valid_numbers = {electrode.number for electrode in self.protocol.electrodes}
        if len(valid_numbers) != self.protocol.electrode_count:
            raise ValueError("Номера электродов протокола должны быть уникальны")
        for channel in self.protocol.channels:
            if not set(channel.drive_pair + channel.measurement_pair) <= valid_numbers:
                raise ValueError(f"Канал {channel.index} ссылается на неизвестный электрод")

    def _normalise_contact_impedances(
        self, values: float | tuple[float, ...] | None
    ) -> np.ndarray:
        if values is None:
            array = np.full(
                self.protocol.electrode_count,
                self.profile.contact_impedance_ohm_m,
                dtype=float,
            )
        elif np.isscalar(values):
            array = np.full(self.protocol.electrode_count, float(values), dtype=float)
        else:
            array = np.asarray(values, dtype=float)
        if array.shape != (self.protocol.electrode_count,):
            raise ValueError("Нужен один контактный импеданс на каждый электрод")
        if not np.isfinite(array).all() or np.any(array <= 0):
            raise ValueError("Контактные импедансы должны быть положительными")
        array.setflags(write=False)
        return array

    @property
    def dimensions(self) -> MatrixDimensions:
        system_size = self.mesh.node_count + self.mesh.electrode_count + 1
        return MatrixDimensions(
            node_count=self.mesh.node_count,
            element_count=self.mesh.element_count,
            electrode_count=self.mesh.electrode_count,
            drive_count=len(self.drive_pairs),
            channel_count=self.protocol.expected_channel_count,
            system_shape=(system_size, system_size),
            jacobian_shape=(self.protocol.expected_channel_count, self.mesh.element_count),
        )

    @property
    def validated_for_real_data(self) -> bool:
        """Все ли геометрические и протокольные предпосылки подтверждены."""

        return bool(
            self.profile.physical_parameters_confirmed
            and self.protocol.channel_order_confirmed
            and self.protocol.electrode_order_confirmed
        )

    def _assemble_boundary_matrix(self) -> np.ndarray:
        n_nodes = self.mesh.node_count
        n_electrodes = self.mesh.electrode_count
        matrix = np.zeros((n_nodes + n_electrodes + 1,) * 2, dtype=float)
        electrode_offset = n_nodes
        for electrode_index, edge_indices in enumerate(self.mesh.electrode_edges):
            inv_z = 1.0 / self.contact_impedances[electrode_index]
            electrode_dof = electrode_offset + electrode_index
            total_length = 0.0
            for edge_index in edge_indices:
                a, b = self.mesh.boundary_edges[edge_index]
                length = float(np.linalg.norm(self.mesh.nodes[a] - self.mesh.nodes[b]))
                total_length += length
                local_mass = inv_z * length / 6.0 * np.array(((2.0, 1.0), (1.0, 2.0)))
                matrix[np.ix_((a, b), (a, b))] += local_mass
                coupling = inv_z * length / 2.0
                matrix[a, electrode_dof] -= coupling
                matrix[b, electrode_dof] -= coupling
                matrix[electrode_dof, a] -= coupling
                matrix[electrode_dof, b] -= coupling
            matrix[electrode_dof, electrode_dof] += inv_z * total_length
        constraint = n_nodes + n_electrodes
        electrode_slice = slice(n_nodes, n_nodes + n_electrodes)
        matrix[constraint, electrode_slice] = 1.0
        matrix[electrode_slice, constraint] = 1.0
        return matrix

    def _conductivity_vector(self, conductivity: float | np.ndarray) -> np.ndarray:
        if np.isscalar(conductivity):
            vector = np.full(self.mesh.element_count, float(conductivity), dtype=float)
        else:
            vector = np.asarray(conductivity, dtype=float)
        if vector.shape != (self.mesh.element_count,):
            raise ValueError(
                f"Проводимость должна иметь форму ({self.mesh.element_count},)"
            )
        if not np.isfinite(vector).all() or np.any(vector <= 0):
            raise ValueError("Проводимость элементов должна быть положительной и конечной")
        return np.ascontiguousarray(vector)

    def conductivity_vector(self, conductivity: float | np.ndarray) -> np.ndarray:
        """Проверить и вернуть независимый вектор проводимости элементов."""

        return self._conductivity_vector(conductivity).copy()

    @staticmethod
    def _conductivity_key(conductivity: np.ndarray) -> str:
        return hashlib.sha256(conductivity.tobytes()).hexdigest()

    def assemble_system(self, conductivity: float | np.ndarray) -> np.ndarray:
        """Собрать симметричную седловую матрицу CEM."""

        sigma = self._conductivity_vector(conductivity)
        matrix = self._boundary_matrix.copy()
        local_stiffness = (
            sigma[:, None, None]
            * self.mesh.element_areas[:, None, None]
            * np.einsum(
                "eik,ejk->eij", self.mesh.shape_gradients, self.mesh.shape_gradients
            )
        )
        for local_a in range(3):
            global_a = self.mesh.elements[:, local_a]
            for local_b in range(3):
                global_b = self.mesh.elements[:, local_b]
                np.add.at(
                    matrix,
                    (global_a, global_b),
                    local_stiffness[:, local_a, local_b],
                )
        return matrix

    def _electrode_rhs(self, pair: tuple[int, int], amplitude: float) -> np.ndarray:
        rhs = np.zeros(self.dimensions.system_shape[0], dtype=float)
        offset = self.mesh.node_count
        rhs[offset + self._electrode_index[pair[0]]] = amplitude
        rhs[offset + self._electrode_index[pair[1]]] = -amplitude
        return rhs

    def _solution_bundle(
        self, conductivity: np.ndarray, current_amperes: float
    ) -> _SolutionBundle:
        key = (self._conductivity_key(conductivity), float(current_amperes))
        cached = self._solution_cache.get(key)
        if cached is not None:
            self._solution_cache.move_to_end(key)
            return cached

        system = self.assemble_system(conductivity)
        drive_rhs = [self._electrode_rhs(pair, current_amperes) for pair in self.drive_pairs]
        measurement_rhs = [
            self._electrode_rhs(pair, 1.0) for pair in self.measurement_pairs
        ]
        rhs = np.column_stack(drive_rhs + measurement_rhs)
        solutions = np.linalg.solve(system, rhs)
        split = len(drive_rhs)
        n_nodes = self.mesh.node_count
        n_electrodes = self.mesh.electrode_count
        bundle = _SolutionBundle(
            system_matrix=system,
            drive_node_potentials=solutions[:n_nodes, :split].T,
            drive_electrode_potentials=solutions[
                n_nodes : n_nodes + n_electrodes, :split
            ].T,
            measurement_adjoint_nodes=solutions[:n_nodes, split:].T,
        )
        self._solution_cache[key] = bundle
        while len(self._solution_cache) > 4:
            self._solution_cache.popitem(last=False)
        return bundle

    def solve(
        self,
        conductivity: float | np.ndarray | None = None,
        *,
        current_amperes: float = 1.0,
    ) -> ForwardResult:
        """Рассчитать напряжения во всех каналах в порядке протокола."""

        if not math.isfinite(current_amperes) or current_amperes <= 0:
            raise ValueError("Амплитуда тока должна быть положительным конечным числом")
        if conductivity is None:
            conductivity = self.profile.background_conductivity_s_m
        sigma = self._conductivity_vector(conductivity)
        bundle = self._solution_bundle(sigma, current_amperes)
        measurements = np.empty(self.protocol.expected_channel_count, dtype=float)
        for channel in self.protocol.channels:
            drive = self._drive_index[channel.drive_pair]
            first, second = channel.measurement_pair
            measurements[channel.index] = (
                bundle.drive_electrode_potentials[drive, self._electrode_index[first]]
                - bundle.drive_electrode_potentials[drive, self._electrode_index[second]]
            )
        return ForwardResult(
            measurements=measurements,
            electrode_potentials=bundle.drive_electrode_potentials.copy(),
            node_potentials=bundle.drive_node_potentials.copy(),
            drive_pairs=self.drive_pairs,
            current_amperes=float(current_amperes),
        )

    def jacobian(
        self,
        conductivity: float | np.ndarray | None = None,
        *,
        current_amperes: float = 1.0,
    ) -> np.ndarray:
        """Рассчитать ``dV[channel] / dσ[element]`` методом сопряжённых полей."""

        if not math.isfinite(current_amperes) or current_amperes <= 0:
            raise ValueError("Амплитуда тока должна быть положительным конечным числом")
        if conductivity is None:
            conductivity = self.profile.background_conductivity_s_m
        sigma = self._conductivity_vector(conductivity)
        key = (self._conductivity_key(sigma), float(current_amperes))
        cached = self._jacobian_cache.get(key)
        if cached is not None:
            self._jacobian_cache.move_to_end(key)
            return cached.copy()
        bundle = self._solution_bundle(sigma, current_amperes)
        drive_gradients = np.einsum(
            "dei,eij->dej",
            bundle.drive_node_potentials[:, self.mesh.elements],
            self.mesh.shape_gradients,
        )
        measurement_gradients = np.einsum(
            "mei,eij->mej",
            bundle.measurement_adjoint_nodes[:, self.mesh.elements],
            self.mesh.shape_gradients,
        )
        jacobian = np.empty(self.dimensions.jacobian_shape, dtype=float)
        for channel in self.protocol.channels:
            drive = self._drive_index[channel.drive_pair]
            measurement = self._measurement_index[channel.measurement_pair]
            jacobian[channel.index] = -self.mesh.element_areas * np.einsum(
                "en,en->e",
                drive_gradients[drive],
                measurement_gradients[measurement],
            )
        if not np.isfinite(jacobian).all():
            raise RuntimeError("Якобиан содержит нечисловые или бесконечные значения")
        self._jacobian_cache[key] = jacobian.copy()
        while len(self._jacobian_cache) > 4:
            self._jacobian_cache.popitem(last=False)
        return jacobian

    def element_values_to_pixels(self, values: np.ndarray, size: int = 64) -> np.ndarray:
        """Перенести постоянные значения элементов на квадратную пиксельную карту."""

        element_values = np.asarray(values, dtype=float)
        if element_values.shape != (self.mesh.element_count,):
            raise ValueError(f"Значения КЭ должны иметь форму ({self.mesh.element_count},)")
        if size < 4:
            raise ValueError("Размер пиксельной карты должен быть не меньше 4")
        projection = self._projection_cache.get(size)
        if projection is None:
            projection = self._build_pixel_projection(size)
            self._projection_cache[size] = projection
        flat = np.full(size * size, np.nan, dtype=float)
        assigned = projection >= 0
        flat[assigned] = element_values[projection[assigned]]
        return flat.reshape(size, size)

    def _build_pixel_projection(self, size: int) -> np.ndarray:
        extent = float(np.max(np.abs(self.mesh.nodes)))
        axis = np.linspace(-extent, extent, size)
        xx, yy = np.meshgrid(axis, axis[::-1])
        points = np.column_stack((xx.ravel(), yy.ravel()))
        assignment = np.full(len(points), -1, dtype=np.int64)
        tolerance = 1e-12 * max(1.0, extent)
        for element_index, element in enumerate(self.mesh.elements):
            triangle = self.mesh.nodes[element]
            lo = triangle.min(axis=0) - tolerance
            hi = triangle.max(axis=0) + tolerance
            candidates = np.flatnonzero(
                (assignment < 0)
                & (points[:, 0] >= lo[0])
                & (points[:, 0] <= hi[0])
                & (points[:, 1] >= lo[1])
                & (points[:, 1] <= hi[1])
            )
            if not len(candidates):
                continue
            p = points[candidates]
            a, b, c = triangle
            cross_ab = (b[0] - a[0]) * (p[:, 1] - a[1]) - (b[1] - a[1]) * (
                p[:, 0] - a[0]
            )
            cross_bc = (c[0] - b[0]) * (p[:, 1] - b[1]) - (c[1] - b[1]) * (
                p[:, 0] - b[0]
            )
            cross_ca = (a[0] - c[0]) * (p[:, 1] - c[1]) - (a[1] - c[1]) * (
                p[:, 0] - c[0]
            )
            inside = (cross_ab >= -tolerance) & (cross_bc >= -tolerance) & (
                cross_ca >= -tolerance
            )
            assignment[candidates[inside]] = element_index
        return assignment

    def clear_numeric_cache(self) -> None:
        self._solution_cache.clear()
        self._jacobian_cache.clear()
        self._projection_cache.clear()

    def cache_info(self) -> dict[str, int]:
        return {
            "systems_and_solutions": len(self._solution_cache),
            "jacobians": len(self._jacobian_cache),
            "pixel_projections": len(self._projection_cache),
        }

