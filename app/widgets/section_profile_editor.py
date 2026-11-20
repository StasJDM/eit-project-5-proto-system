"""Engineering editor for selectable and custom EIT cross-section profiles."""

from __future__ import annotations

import math
from uuid import uuid4

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPalette, QPen, QPolygonF,
)
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QStyledItemDelegate,
    QVBoxLayout, QWidget,
)

from ..i18n import t
from ..reconstruction.geometry import (
    CONTOUR_SAMPLE_COUNT, LUNG_CONTOUR_SAMPLE_COUNT, GeometryProfile,
    builtin_geometry_profiles, ellipse_profile,
)
from ..styles import C


class _TouchComboDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:
        size = super().sizeHint(option, index)
        size.setHeight(max(48, size.height()))
        return size


def _configure_section_combo(combo: QComboBox) -> None:
    """Keep section-editor popup choices readable and touch-friendly on macOS."""
    combo.setMinimumHeight(48)
    combo.setMaxVisibleItems(8)
    combo.setItemDelegate(_TouchComboDelegate(combo))
    combo.setStyleSheet(f"""
        QComboBox {{
            background-color:{C['bg_card']};
            color:{C['text']};
            border:1px solid {C['border_light']};
            border-radius:6px;
            padding:7px 40px 7px 12px;
            font-size:18px;
        }}
        QComboBox:focus {{ border-color:{C['blue_light']}; }}
        QComboBox:disabled {{
            background-color:{C['bg_panel']};
            color:{C['text_dim']};
            border-color:{C['border']};
        }}
        QComboBox::drop-down {{
            border:none;
            width:36px;
        }}
        QComboBox QAbstractItemView {{
            background-color:{C['bg_panel']};
            color:{C['text']};
            border:1px solid {C['border_light']};
            outline:0;
            selection-background-color:{C['blue']};
            selection-color:{C['text']};
        }}
        QComboBox QListView::item {{
            min-height:44px;
            padding:4px 12px;
        }}
    """)

    # The popup is a top-level native window on macOS and may not inherit the
    # combo's stylesheet. Apply its palette and rules directly as well.
    view = combo.view()
    palette = view.palette()
    palette.setColor(QPalette.Base, QColor(C["bg_panel"]))
    palette.setColor(QPalette.Window, QColor(C["bg_panel"]))
    palette.setColor(QPalette.Text, QColor(C["text"]))
    palette.setColor(QPalette.WindowText, QColor(C["text"]))
    palette.setColor(QPalette.Highlight, QColor(C["blue"]))
    palette.setColor(QPalette.HighlightedText, QColor(C["text"]))
    view.setPalette(palette)
    view.setStyleSheet(f"""
        QAbstractItemView {{
            background-color:{C['bg_panel']};
            color:{C['text']};
            border:1px solid {C['border_light']};
            outline:0;
            selection-background-color:{C['blue']};
            selection-color:{C['text']};
        }}
        QListView::item {{ min-height:44px;padding:4px 12px; }}
    """)


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
        self._drag_mode: str | None = None
        self._drag_start_screen = QPointF()
        self._drag_start_center = (0.0, 0.0)
        self.editable = False
        self.edit_target = "section"

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

    def _lung_screen_point(self, side: str, index: int) -> tuple[float, float]:
        cx, cy, scale = self._center_and_scale()
        x, y = self._profile.lung_point(side, index)
        # Present the patient in direct orientation, as in LungVizWidget.
        return cx - x * scale, cy - y * scale

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

        if self._profile.lungs_enabled:
            for side in ("left", "right"):
                lung_points = [
                    self._lung_screen_point(side, index)
                    for index in range(LUNG_CONTOUR_SAMPLE_COUNT)
                ]
                lung_path = QPainterPath()
                lung_path.moveTo(*lung_points[0])
                for point in lung_points[1:]:
                    lung_path.lineTo(*point)
                lung_path.closeSubpath()
                active = self.edit_target == side
                painter.setBrush(QColor(190, 177, 151, 75))
                painter.setPen(QPen(QColor("#ffc857" if active else "#bdb39f"), 2))
                painter.drawPath(lung_path)
                if active:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor("#ffc857" if self.editable else C["text_dim"]))
                    for x, y in lung_points:
                        painter.drawEllipse(int(x - 3), int(y - 3), 6, 6)
                    center_x, center_y = self._profile.lung_center(side)
                    center_screen_x = cx - center_x * self._profile.radius_m * _scale
                    center_screen_y = cy - center_y * self._profile.radius_m * _scale
                    painter.setPen(QPen(QColor("#ffc857"), 2))
                    painter.setBrush(QColor(C["bg_card"]))
                    painter.drawEllipse(
                        QPointF(center_screen_x, center_screen_y), 9.0, 9.0
                    )
                    painter.drawLine(
                        QPointF(center_screen_x - 5.0, center_screen_y),
                        QPointF(center_screen_x + 5.0, center_screen_y),
                    )
                    painter.drawLine(
                        QPointF(center_screen_x, center_screen_y - 5.0),
                        QPointF(center_screen_x, center_screen_y + 5.0),
                    )

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffc857" if self.editable else C["text_dim"]))
        if self.edit_target == "section":
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
            self._drag_mode = "reshape"
            if (
                self.edit_target in {"left", "right"}
                and self._profile.lungs_enabled
                and self._lung_hit_mode(
                    self.edit_target, event.position().x(), event.position().y()
                ) == "move"
            ):
                self._drag_mode = "move"
                self._drag_start_screen = event.position()
                self._drag_start_center = self._profile.lung_center(self.edit_target)
                self.setCursor(Qt.ClosedHandCursor)
                return
            self._edit_at(event.position().x(), event.position().y())

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            if self._drag_mode == "move":
                self._move_lung_to(event.position().x(), event.position().y())
            else:
                self._edit_at(event.position().x(), event.position().y())

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            self._drag_mode = None
            self.setCursor(Qt.CrossCursor if self.editable else Qt.ArrowCursor)
            self.profile_edit_finished.emit(self._profile)

    def _lung_hit_mode(self, side: str, screen_x: float, screen_y: float) -> str:
        point = QPointF(screen_x, screen_y)
        lung_points = [
            QPointF(*self._lung_screen_point(side, index))
            for index in range(LUNG_CONTOUR_SAMPLE_COUNT)
        ]
        if any(
            math.hypot(point.x() - handle.x(), point.y() - handle.y()) <= 14.0
            for handle in lung_points
        ):
            return "reshape"
        if QPolygonF(lung_points).containsPoint(point, Qt.OddEvenFill):
            return "move"
        return "reshape"

    def _move_lung_to(self, screen_x: float, screen_y: float) -> None:
        _cx, _cy, scale = self._center_and_scale()
        delta_x = screen_x - self._drag_start_screen.x()
        delta_y = screen_y - self._drag_start_screen.y()
        normalized_scale = max(self._profile.radius_m * scale, 1e-9)
        requested = (
            self._drag_start_center[0] - delta_x / normalized_scale,
            self._drag_start_center[1] - delta_y / normalized_scale,
        )
        edited = self._profile.with_lung_center(self.edit_target, requested)
        self.set_profile(edited)
        self.profile_edited.emit(edited)

    def _edit_at(self, screen_x: float, screen_y: float) -> None:
        cx, cy, scale = self._center_and_scale()
        if self.edit_target in {"left", "right"} and self._profile.lungs_enabled:
            # Lung contours use direct patient orientation on screen.
            x, y = -(screen_x - cx) / scale, -(screen_y - cy) / scale
            center_x_factor, center_y_factor = self._profile.lung_center(
                self.edit_target
            )
            center_x = self._profile.radius_m * center_x_factor
            center_y = self._profile.radius_m * center_y_factor
            normalized_x = (x - center_x) / (self._profile.radius_m * 0.235)
            normalized_y = (y - center_y) / (self._profile.radius_m * 0.46)
            angle = math.atan2(normalized_y, normalized_x) % (2.0 * math.pi)
            index = round(
                angle * LUNG_CONTOUR_SAMPLE_COUNT / (2.0 * math.pi)
            ) % LUNG_CONTOUR_SAMPLE_COUNT
            factor = max(0.35, min(1.45, math.hypot(normalized_x, normalized_y)))
            factors = list(self._profile.lung_radius_factors(self.edit_target))
            indices = {index}
            if self.horizontal_symmetry:
                indices.add((-index) % LUNG_CONTOUR_SAMPLE_COUNT)
            if self.vertical_symmetry:
                indices.update(
                    (LUNG_CONTOUR_SAMPLE_COUNT // 2 - item)
                    % LUNG_CONTOUR_SAMPLE_COUNT
                    for item in tuple(indices)
                )
            for item in indices:
                factors[item] = factor
            edited = self._profile.with_lung_contour(
                self.edit_target, tuple(factors)
            )
            self.set_profile(edited)
            self.profile_edited.emit(edited)
            return

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
        _configure_section_combo(self.profile_combo)
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

        self.lungs_check = QCheckBox(t("sys_section_lungs_enabled"))
        self.lungs_check.setChecked(True)
        self.lungs_check.toggled.connect(self._lungs_toggled)
        controls.addWidget(self.lungs_check)
        self.edit_target_label = QLabel(t("sys_section_edit_target"))
        controls.addWidget(self.edit_target_label)
        self.edit_target_combo = QComboBox()
        self.edit_target_combo.addItem(t("sys_section_target_section"), "section")
        self.edit_target_combo.addItem(t("sys_section_target_left_lung"), "left")
        self.edit_target_combo.addItem(t("sys_section_target_right_lung"), "right")
        _configure_section_combo(self.edit_target_combo)
        self.edit_target_combo.currentIndexChanged.connect(self._edit_target_changed)
        controls.addWidget(self.edit_target_combo)

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
        self.lungs_check.setText(t("sys_section_lungs_enabled"))
        self.edit_target_label.setText(t("sys_section_edit_target"))
        for index, key in enumerate((
            "sys_section_target_section",
            "sys_section_target_left_lung",
            "sys_section_target_right_lung",
        )):
            self.edit_target_combo.setItemText(index, t(key))
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
        self.lungs_check.setChecked(profile.lungs_enabled)
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
            self.lungs_check,
        ):
            widget.setEnabled(editable)
        self.edit_target_combo.setEnabled(
            editable and (
                profile.lungs_enabled
                or self.edit_target_combo.currentData() == "section"
            )
        )
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
            lungs_enabled=self._active.lungs_enabled,
            left_lung_radius_factors=self._active.left_lung_radius_factors,
            right_lung_radius_factors=self._active.right_lung_radius_factors,
            left_lung_center=self._active.left_lung_center,
            right_lung_center=self._active.right_lung_center,
        )
        self._record_change(profile)

    def _radial_edited(self, profile: GeometryProfile) -> None:
        if not self._is_editable():
            return
        self._active = profile
        self.canvas.set_profile(profile)
        self._update_action_state()

    def _finish_radial_edit(self, profile: GeometryProfile) -> None:
        if self._is_editable():
            self._record_change(profile)

    def _smooth(self) -> None:
        if not self._is_editable():
            return
        target = str(self.edit_target_combo.currentData())
        if target in {"left", "right"}:
            factors = self._active.lung_radius_factors(target)
            smoothed = tuple(
                (factors[index - 1] + 2.0 * factors[index] + factors[(index + 1) % len(factors)])
                / 4.0
                for index in range(len(factors))
            )
            self._record_change(self._active.with_lung_contour(target, smoothed))
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

    def _lungs_toggled(self, checked: bool) -> None:
        if self._loading or not self._is_editable():
            return
        if not checked and self.edit_target_combo.currentData() != "section":
            self.edit_target_combo.setCurrentIndex(0)
        self._record_change(self._active.with_lungs_enabled(checked))

    def _edit_target_changed(self, _index: int) -> None:
        target = str(self.edit_target_combo.currentData())
        if target in {"left", "right"} and not self._active.lungs_enabled:
            target = "section"
            self.edit_target_combo.setCurrentIndex(0)
        self.canvas.edit_target = target
        self.canvas.update()

