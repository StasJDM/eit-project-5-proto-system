"""Детерминированная треугольная сетка звездообразного 2D-контура."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

import numpy as np

from .geometry import GeometryProfile
from .protocol import MeasurementProtocol


class MeshDensity(str, Enum):
    LOW = "низкая"
    MEDIUM = "средняя"
    HIGH = "высокая"


_DENSITY_SHAPES = {
    MeshDensity.LOW: (4, 32),
    MeshDensity.MEDIUM: (6, 64),
    MeshDensity.HIGH: (8, 96),
}


@dataclass(frozen=True)
class FiniteElementMesh:
    """Линейная треугольная КЭ-сетка и разбиение границы на электроды."""

    nodes: np.ndarray
    elements: np.ndarray
    boundary_edges: np.ndarray
    electrode_edges: tuple[tuple[int, ...], ...]
    element_areas: np.ndarray
    shape_gradients: np.ndarray
    geometry_profile_id: str
    density: MeshDensity

    @property
    def node_count(self) -> int:
        return int(self.nodes.shape[0])

    @property
    def element_count(self) -> int:
        return int(self.elements.shape[0])

    @property
    def electrode_count(self) -> int:
        return len(self.electrode_edges)

    def validate(self) -> None:
        if self.nodes.ndim != 2 or self.nodes.shape[1] != 2:
            raise ValueError("Координаты узлов должны иметь форму (N, 2)")
        if self.elements.ndim != 2 or self.elements.shape[1] != 3:
            raise ValueError("Треугольники должны иметь форму (E, 3)")
        if np.min(self.elements) < 0 or np.max(self.elements) >= self.node_count:
            raise ValueError("Сетка содержит ссылку на несуществующий узел")
        if not np.isfinite(self.nodes).all() or not np.isfinite(self.element_areas).all():
            raise ValueError("Сетка содержит нечисловые или бесконечные значения")
        if np.any(self.element_areas <= 0):
            raise ValueError("Все треугольники должны иметь положительную площадь")
        if self.shape_gradients.shape != (self.element_count, 3, 2):
            raise ValueError("Градиенты функций формы имеют неверную размерность")
        if any(not edges for edges in self.electrode_edges):
            raise ValueError("Каждый электрод должен содержать хотя бы одно ребро")


def _element_geometry(nodes: np.ndarray, elements: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    points = nodes[elements]
    x1, y1 = points[:, 0, 0], points[:, 0, 1]
    x2, y2 = points[:, 1, 0], points[:, 1, 1]
    x3, y3 = points[:, 2, 0], points[:, 2, 1]
    twice_area = (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)
    if np.any(twice_area <= 0):
        raise ValueError("Обнаружен вырожденный или ориентированный по часовой стрелке КЭ")
    gradients = np.empty((len(elements), 3, 2), dtype=float)
    gradients[:, 0, 0] = (y2 - y3) / twice_area
    gradients[:, 0, 1] = (x3 - x2) / twice_area
    gradients[:, 1, 0] = (y3 - y1) / twice_area
    gradients[:, 1, 1] = (x1 - x3) / twice_area
    gradients[:, 2, 0] = (y1 - y2) / twice_area
    gradients[:, 2, 1] = (x2 - x1) / twice_area
    return twice_area / 2.0, gradients


def generate_mesh(
    profile: GeometryProfile,
    protocol: MeasurementProtocol,
    density: MeshDensity | str = MeshDensity.MEDIUM,
) -> FiniteElementMesh:
    """Построить полярно-слоистую сетку и сопоставить граничные рёбра электродам."""

    density = MeshDensity(density)
    radial_layers, angular_segments = _DENSITY_SHAPES[density]
    if angular_segments % protocol.electrode_count:
        raise ValueError("Число граничных сегментов должно делиться на число электродов")

    angles = np.arange(angular_segments, dtype=float) * 2 * math.pi / angular_segments
    boundary_radii = np.array([profile.radius_at(float(angle)) for angle in angles])
    node_rows = [np.zeros((1, 2), dtype=float)]
    for layer in range(1, radial_layers + 1):
        fraction = layer / radial_layers
        radii = boundary_radii * fraction
        node_rows.append(np.column_stack((radii * np.cos(angles), radii * np.sin(angles))))
    nodes = np.vstack(node_rows)

    def node_index(layer: int, angular: int) -> int:
        if layer == 0:
            return 0
        return 1 + (layer - 1) * angular_segments + angular % angular_segments

    triangles: list[tuple[int, int, int]] = []
    for angular in range(angular_segments):
        triangles.append((0, node_index(1, angular), node_index(1, angular + 1)))
    for layer in range(2, radial_layers + 1):
        for angular in range(angular_segments):
            inner_a = node_index(layer - 1, angular)
            inner_b = node_index(layer - 1, angular + 1)
            outer_a = node_index(layer, angular)
            outer_b = node_index(layer, angular + 1)
            triangles.append((inner_a, outer_a, outer_b))
            triangles.append((inner_a, outer_b, inner_b))
    elements = np.asarray(triangles, dtype=np.int64)

    boundary_edges = np.asarray(
        [
            (node_index(radial_layers, angular), node_index(radial_layers, angular + 1))
            for angular in range(angular_segments)
        ],
        dtype=np.int64,
    )
    edge_mid_angles = (angles + math.pi / angular_segments) % (2 * math.pi)
    electrode_half_width = (
        math.pi / protocol.electrode_count * profile.electrode_width_fraction
    )
    electrode_edges: list[tuple[int, ...]] = []
    for electrode in protocol.electrodes:
        center = math.radians(electrode.angle_degrees) % (2 * math.pi)
        distance = np.abs((edge_mid_angles - center + math.pi) % (2 * math.pi) - math.pi)
        selected = tuple(int(index) for index in np.flatnonzero(distance <= electrode_half_width + 1e-12))
        if not selected:
            selected = (int(np.argmin(distance)),)
        electrode_edges.append(selected)

    areas, gradients = _element_geometry(nodes, elements)
    for array in (nodes, elements, boundary_edges, areas, gradients):
        array.setflags(write=False)
    mesh = FiniteElementMesh(
        nodes=nodes,
        elements=elements,
        boundary_edges=boundary_edges,
        electrode_edges=tuple(electrode_edges),
        element_areas=areas,
        shape_gradients=gradients,
        geometry_profile_id=profile.profile_id,
        density=density,
    )
    mesh.validate()
    return mesh

