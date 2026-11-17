"""Engineering editor for selectable and custom EIT cross-section profiles."""

from __future__ import annotations

import math
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..i18n import t
from ..reconstruction.geometry import (
    CONTOUR_SAMPLE_COUNT, GeometryProfile, builtin_geometry_profiles,
    ellipse_profile,
)
from ..styles import C


def _sample_factors(profile: GeometryProfile) -> tuple[float, ...]:
    return tuple(
        profile.radius_at(2.0 * math.pi * index / CONTOUR_SAMPLE_COUNT)
        / profile.radius_m
        for index in range(CONTOUR_SAMPLE_COUNT)
    )


def _dimensions_mm(profile: GeometryProfile) -> tuple[float, float]:
    points = []
    for index in range(256):
        angle = 2.0 * math.pi * index / 256
        radius = profile.radius_at(angle)
        points.append((radius * math.cos(angle), radius * math.sin(angle)))
    xs, ys = zip(*points)
    return (max(xs) - min(xs)) * 1000.0, (max(ys) - min(ys)) * 1000.0


def _profile_state_key(profile: GeometryProfile) -> tuple[object, ...]:
    """Editor state includes the name, unlike the numeric GREIT cache key."""

    return profile.cache_key(), profile.display_name


class SectionContourCanvas(QWidget):
    """Drag radial handles while preserving the star-shaped mesh contract."""

    profile_edited = Signal(object)
    profile_edit_finished = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(340, 300)
        self._profile = builtin_geometry_profiles()[0]
        self.vertical_symmetry = True
        self.horizontal_symmetry = True
        self._dragging = False
        self.editable = False

    @property
    def profile(self) -> GeometryProfile:
        return self._profile

    def set_profile(self, profile: GeometryProfile) -> None:
        self._profile = profile
        self.update()

    def _center_and_scale(self) -> tuple[float, float, float]:
        scale = min(self.width(), self.height()) / (2.0 * self._profile.radius_m * 1.3)
        return self.width() / 2.0, self.height() / 2.0, scale

    def _screen_point(self, angle: float, radius: float) -> tuple[float, float]:
        cx, cy, scale = self._center_and_scale()
        return (
            cx + radius * math.cos(angle) * scale,
            cy - radius * math.sin(angle) * scale,
        )

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(C["bg_card"]))
        cx, cy, _scale = self._center_and_scale()
        painter.setPen(QPen(QColor(C["border"]), 1, Qt.DashLine))
        painter.drawLine(12, int(cy), self.width() - 12, int(cy))
        painter.drawLine(int(cx), 12, int(cx), self.height() - 12)

        path = QPainterPath()
        points = []
        for index in range(CONTOUR_SAMPLE_COUNT):
            angle = 2.0 * math.pi * index / CONTOUR_SAMPLE_COUNT
            points.append(self._screen_point(angle, self._profile.radius_at(angle)))
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        path.closeSubpath()
        painter.setBrush(QColor(41, 182, 209, 35))
        painter.setPen(QPen(QColor(C["blue_light"]), 2))
        painter.drawPath(path)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffc857" if self.editable else C["text_dim"]))
        for index in range(0, CONTOUR_SAMPLE_COUNT, 2):
            x, y = points[index]
            painter.drawEllipse(int(x - 3), int(y - 3), 6, 6)
        painter.setBrush(QColor("#40c4ff"))
        for index in range(16):
            angle = 2.0 * math.pi * index / 16 - math.pi / 2
            x, y = self._screen_point(angle, self._profile.radius_at(angle))
            painter.drawEllipse(int(x - 4), int(y - 4), 8, 8)

    def mousePressEvent(self, event) -> None:
        if self.editable and event.button() == Qt.LeftButton:
            self._dragging = True
            self._edit_at(event.position().x(), event.position().y())

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._edit_at(event.position().x(), event.position().y())

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            self.profile_edit_finished.emit(self._profile)

    def _edit_at(self, screen_x: float, screen_y: float) -> None:
        cx, cy, scale = self._center_and_scale()
        x, y = (screen_x - cx) / scale, -(screen_y - cy) / scale
        angle = math.atan2(y, x) % (2.0 * math.pi)
        index = round(angle * CONTOUR_SAMPLE_COUNT / (2.0 * math.pi)) % CONTOUR_SAMPLE_COUNT
        factor = max(0.35, min(1.25, math.hypot(x, y) / self._profile.radius_m))
        factors = list(_sample_factors(self._profile))
        indices = {index}
        if self.horizontal_symmetry:
            indices.add((-index) % CONTOUR_SAMPLE_COUNT)
        if self.vertical_symmetry:
            indices.update(
                (CONTOUR_SAMPLE_COUNT // 2 - item) % CONTOUR_SAMPLE_COUNT
                for item in tuple(indices)
            )
        for item in indices:
            factors[item] = factor
        edited = self._profile.with_contour(
            tuple(factors),
            profile_id=self._profile.profile_id,
            display_name=self._profile.display_name,
        )
        self.set_profile(edited)
        self.profile_edited.emit(edited)


class SectionProfileEditor(QWidget):
    """Preset library plus parametric ellipse and advanced radial editor."""

    dirty_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._loading = False
        self._custom_profiles: list[GeometryProfile] = []
        self._active = builtin_geometry_profiles()[0]
        self._pending_new_ids: set[str] = set()
        self._history: list[GeometryProfile] = [self._active]
        self._history_index = 0
        self._dirty = False
        self._name_invalid = False

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(18)
        self.control_scroll = QScrollArea()
        self.control_scroll.setWidgetResizable(True)
        self.control_scroll.setFrameShape(QFrame.NoFrame)
        self.control_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.control_scroll.setMinimumWidth(360)
        self.control_scroll.setMaximumWidth(480)
        self.control_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        control_content = QWidget()
        control_content.setStyleSheet("background: transparent;")
        controls = QVBoxLayout(control_content)
        controls.setContentsMargins(8, 0, 12, 8)
        controls.setSpacing(14)
        self.control_scroll.setWidget(control_content)
        root.addWidget(self.control_scroll, 0)

        self.profile_label = QLabel(t("sys_section_profile"))
        controls.addWidget(self.profile_label)
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(300)
        self.profile_combo.currentIndexChanged.connect(self._select_profile)
        controls.addWidget(self.profile_combo)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton(t("sys_section_copy"))
        self.delete_button = QPushButton(t("sys_section_delete"))
        self.copy_button.clicked.connect(self._copy_profile)
        self.delete_button.clicked.connect(self._delete_profile)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.delete_button)
        controls.addLayout(buttons)

        edit_actions = QHBoxLayout()
        self.reset_button = QPushButton(t("sys_section_reset"))
        self.reset_button.clicked.connect(self._reset_profile)
        edit_actions.addWidget(self.reset_button)
        controls.addLayout(edit_actions)

        history_actions = QHBoxLayout()
        self.undo_button = QPushButton(t("sys_section_undo"))
        self.redo_button = QPushButton(t("sys_section_redo"))
        self.undo_button.clicked.connect(self._undo)
        self.redo_button.clicked.connect(self._redo)
        history_actions.addWidget(self.undo_button)
        history_actions.addWidget(self.redo_button)
        controls.addLayout(history_actions)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(80)
        self.name_edit.setMinimumWidth(200)
        self.name_edit.setFixedHeight(42)
        self.name_edit.textChanged.connect(self._name_changed)
        self.width_spin = self._dimension_spin()
        self.height_spin = self._dimension_spin()
        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(-180.0, 180.0)
        self.rotation_spin.setSuffix("°")
        self._configure_numeric_editor(self.rotation_spin)
        self.name_label = QLabel(t("sys_section_name"))
        self.width_label = QLabel(t("sys_section_width"))
        self.height_label = QLabel(t("sys_section_height"))
        self.rotation_label = QLabel(t("sys_section_rotation"))
        grid.addWidget(self.name_label, 0, 0)
        grid.addWidget(self.name_edit, 0, 1)
        grid.addWidget(self.width_label, 1, 0)
        grid.addWidget(self.width_spin, 1, 1)
        grid.addWidget(self.height_label, 2, 0)
        grid.addWidget(self.height_spin, 2, 1)
        grid.addWidget(self.rotation_label, 3, 0)
        grid.addWidget(self.rotation_spin, 3, 1)
        controls.addLayout(grid)
        for editor in (self.width_spin, self.height_spin, self.rotation_spin):
            editor.valueChanged.connect(self._parametric_changed)

        self.vertical_check = QCheckBox(t("sys_section_vertical_symmetry"))
        self.horizontal_check = QCheckBox(t("sys_section_horizontal_symmetry"))
        self.vertical_check.setChecked(True)
        self.horizontal_check.setChecked(True)
        controls.addWidget(self.vertical_check)
        controls.addWidget(self.horizontal_check)

        self.smooth_button = QPushButton(t("sys_section_smooth"))
        self.smooth_button.clicked.connect(self._smooth)
        controls.addWidget(self.smooth_button)
        self.hint_label = QLabel(t("sys_section_hint"))
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet(f"color:{C['text_dim']};")
        controls.addWidget(self.hint_label)
        controls.addStretch()
        control_content.setMinimumHeight(controls.sizeHint().height())

        self.canvas = SectionContourCanvas()
        self.canvas.profile_edited.connect(self._radial_edited)
        self.canvas.profile_edit_finished.connect(self._finish_radial_edit)
        self.vertical_check.toggled.connect(
            lambda value: setattr(self.canvas, "vertical_symmetry", value)
        )
        self.horizontal_check.toggled.connect(
            lambda value: setattr(self.canvas, "horizontal_symmetry", value)
        )
        root.addWidget(self.canvas, 1)
        self.load(self._active, ())

    def retranslate(self) -> None:
        self.profile_label.setText(t("sys_section_profile"))
        self.copy_button.setText(t("sys_section_copy"))
        self.delete_button.setText(t("sys_section_delete"))
        self.reset_button.setText(t("sys_section_reset"))
        self.undo_button.setText(t("sys_section_undo"))
        self.redo_button.setText(t("sys_section_redo"))
        self.name_label.setText(t("sys_section_name"))
        self.width_label.setText(t("sys_section_width"))
        self.height_label.setText(t("sys_section_height"))
        self.rotation_label.setText(t("sys_section_rotation"))
        self.vertical_check.setText(t("sys_section_vertical_symmetry"))
        self.horizontal_check.setText(t("sys_section_horizontal_symmetry"))
        self.smooth_button.setText(t("sys_section_smooth"))
        self.hint_label.setText(t("sys_section_hint"))

    @staticmethod
    def _dimension_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(50.0, 600.0)
        spin.setDecimals(1)
        spin.setSuffix(" мм")
        SectionProfileEditor._configure_numeric_editor(spin)
        return spin

    @staticmethod
    def _configure_numeric_editor(spin: QDoubleSpinBox) -> None:
        spin.setMinimumWidth(200)
        spin.setFixedHeight(42)
        spin.setStyleSheet(
            "QDoubleSpinBox { padding: 6px 30px 6px 8px; }"
            "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 24px; }"
        )

    @property
    def active_profile(self) -> GeometryProfile:
        return self._saved_profile(self._active.profile_id) or self._active

    @property
    def custom_profiles(self) -> tuple[GeometryProfile, ...]:
        return tuple(self._custom_profiles)

    @property
    def has_unsaved_changes(self) -> bool:
        return self._dirty

    @property
    def can_save(self) -> bool:
        return self._dirty and not self._name_invalid

    def load(
        self, active: GeometryProfile, custom_profiles: tuple[GeometryProfile, ...]
    ) -> None:
        self._custom_profiles = list(custom_profiles)
        self._pending_new_ids.clear()
        self._active = active
        self._refresh_library(active.profile_id)
        self._show_profile(active)

    @staticmethod
    def _builtin_ids() -> set[str]:
        return {item.profile_id for item in builtin_geometry_profiles()}

    def _saved_profile(self, profile_id: str) -> GeometryProfile | None:
        for profile in self._custom_profiles:
            if profile.profile_id == profile_id:
                return profile
        return None

    def _all_profiles(self) -> tuple[GeometryProfile, ...]:
        builtins = builtin_geometry_profiles()
        custom_ids = {profile.profile_id for profile in self._custom_profiles}
        active_extra = (
            (self._active,)
            if self._active.profile_id not in {p.profile_id for p in builtins} | custom_ids
            else ()
        )
        return builtins + tuple(self._custom_profiles) + active_extra

    def _refresh_library(self, selected_id: str) -> None:
        self._loading = True
        self.profile_combo.clear()
        for profile in self._all_profiles():
            self.profile_combo.addItem(profile.display_name, profile.profile_id)
        index = self.profile_combo.findData(selected_id)
        self.profile_combo.setCurrentIndex(max(0, index))
        self._loading = False

    def _show_profile(
        self, profile: GeometryProfile, *, reset_history: bool = True
    ) -> None:
        if reset_history:
            self._history = [profile]
            self._history_index = 0
        self._display_profile(profile)

    def _display_profile(self, profile: GeometryProfile) -> None:
        self._loading = True
        self._active = profile
        self._name_invalid = False
        width, height = (
            (profile.width_m * 1000.0, profile.height_m * 1000.0)
            if profile.shape_kind == "ellipse"
            and profile.width_m is not None
            and profile.height_m is not None
            else _dimensions_mm(profile)
        )
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)
        self.rotation_spin.setValue(profile.rotation_degrees)
        self.name_edit.setText(profile.display_name)
        self.canvas.set_profile(profile)
        editable = profile.profile_id not in self._builtin_ids()
        for widget in (
            self.width_spin,
            self.height_spin,
            self.rotation_spin,
            self.name_edit,
            self.vertical_check,
            self.horizontal_check,
            self.smooth_button,
        ):
            widget.setEnabled(editable)
        self.canvas.editable = editable
        self.canvas.setCursor(Qt.CrossCursor if editable else Qt.ArrowCursor)
        self.delete_button.setEnabled(editable)
        self._loading = False
        self._update_action_state()

    def _select_profile(self, _index: int) -> None:
        if self._loading:
            return
        profile_id = self.profile_combo.currentData()
        for profile in self._all_profiles():
            if profile.profile_id == profile_id:
                self._show_profile(profile)
                return

    def _custom_name(self, base: str) -> str:
        return f"{base} — копия {len(self._custom_profiles) + 1}"

    def _is_editable(self) -> bool:
        return self._active.profile_id not in self._builtin_ids()

    def _record_change(self, profile: GeometryProfile) -> None:
        if not self._is_editable():
            return
        current = self._history[self._history_index]
        if _profile_state_key(profile) != _profile_state_key(current):
            del self._history[self._history_index + 1:]
            self._history.append(profile)
            self._history_index = len(self._history) - 1
        self._display_profile(profile)

    def _update_action_state(self) -> None:
        editable = self._is_editable()
        saved = self._saved_profile(self._active.profile_id)
        dirty = editable and saved is not None and (
            _profile_state_key(saved) != _profile_state_key(self._active)
            or self._active.profile_id in self._pending_new_ids
            or self._name_invalid
        )
        self._dirty = dirty
        self.dirty_changed.emit(dirty)
        self.reset_button.setEnabled(dirty)
        self.undo_button.setEnabled(editable and self._history_index > 0)
        self.redo_button.setEnabled(
            editable and self._history_index + 1 < len(self._history)
        )

    def _copy_profile(self) -> None:
        source = self._active
        custom = source.with_identity(
            profile_id=f"custom-section-{uuid4().hex[:10]}",
            display_name=self._custom_name(source.display_name),
        )
        self._custom_profiles.append(custom)
        self._pending_new_ids.add(custom.profile_id)
        self._active = custom
        self._refresh_library(custom.profile_id)
        self._show_profile(custom)

    def _delete_profile(self) -> None:
        before = len(self._custom_profiles)
        self._custom_profiles = [
            item for item in self._custom_profiles
            if item.profile_id != self._active.profile_id
        ]
        if len(self._custom_profiles) == before:
            return
        self._pending_new_ids.discard(self._active.profile_id)
        self._active = builtin_geometry_profiles()[0]
        self._refresh_library(self._active.profile_id)
        self._show_profile(self._active)

    def save_profile(self) -> None:
        if not self._is_editable() or not self.can_save:
            return
        self._active = self._active.with_identity(
            profile_id=self._active.profile_id,
            display_name=self.name_edit.text().strip(),
        )
        for index, item in enumerate(self._custom_profiles):
            if item.profile_id == self._active.profile_id:
                self._custom_profiles[index] = self._active
                break
        else:
            self._custom_profiles.append(self._active)
        self._pending_new_ids.discard(self._active.profile_id)
        self._refresh_library(self._active.profile_id)
        self._update_action_state()

    def _name_changed(self, text: str) -> None:
        if self._loading or not self._is_editable():
            return
        self._name_invalid = not bool(text.strip())
        if self._name_invalid:
            self._update_action_state()
            return
        renamed = self._active.with_identity(
            profile_id=self._active.profile_id,
            display_name=text,
        )
        current = self._history[self._history_index]
        if _profile_state_key(renamed) != _profile_state_key(current):
            del self._history[self._history_index + 1:]
            self._history.append(renamed)
            self._history_index = len(self._history) - 1
        self._active = renamed
        self._update_action_state()

    def _reset_profile(self) -> None:
        saved = self._saved_profile(self._active.profile_id)
        if saved is not None:
            self._record_change(saved)

    def _undo(self) -> None:
        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._display_profile(self._history[self._history_index])

    def _redo(self) -> None:
        if self._history_index + 1 >= len(self._history):
            return
        self._history_index += 1
        self._display_profile(self._history[self._history_index])

    def _parametric_changed(self, _value: float) -> None:
        if self._loading:
            return
        if not self._is_editable():
            return
        profile = ellipse_profile(
            width_m=self.width_spin.value() / 1000.0,
            height_m=self.height_spin.value() / 1000.0,
            rotation_degrees=self.rotation_spin.value(),
            profile_id=self._active.profile_id,
            display_name=self._active.display_name,
        )
        self._record_change(profile)

    def _radial_edited(self, profile: GeometryProfile) -> None:
        if not self._is_editable():
            return
        edited = profile.with_contour(
            _sample_factors(profile),
            profile_id=self._active.profile_id,
            display_name=self._active.display_name,
        )
        self._active = edited
        self.canvas.set_profile(edited)
        self._update_action_state()

    def _finish_radial_edit(self, profile: GeometryProfile) -> None:
        if self._is_editable():
            self._record_change(profile)

    def _smooth(self) -> None:
        if not self._is_editable():
            return
        factors = _sample_factors(self._active)
        smoothed = tuple(
            (factors[index - 1] + 2.0 * factors[index] + factors[(index + 1) % len(factors)])
            / 4.0
            for index in range(len(factors))
        )
        profile = self._active.with_contour(
            smoothed,
            profile_id=self._active.profile_id,
            display_name=self._active.display_name,
        )
        self._record_change(profile)

