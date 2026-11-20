import os
import unittest
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QScrollArea, QStyleOptionViewItem,
)
from PySide6.QtGui import QColor, QPalette, QValidator
from PySide6.QtTest import QTest

from app.application import (
    ALL_INTERFACE_ELEMENTS,
    AerationAlgorithmParameters,
    EngineeringSettings,
    EngineeringSettingsService,
    EventBus,
    EventType,
    INTERFACE_ELEMENTS,
    INTERFACE_TABS,
    MonitoringService,
    calculate_aeration_metrics,
)
from app.data_sources import SimulationDataSource
from app.screens.system_info_screen import SystemInfoScreen
from app.screens.trends_screen import _MetricValueTable
from app.widgets.waveform_panel import RegionalWaveformPanel, WaveformPanel
from app.widgets.section_profile_editor import SectionProfileEditor
from app.reconstruction import ellipse_profile
from app.i18n import i18n


class MemorySettingsRepository:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def load(self):
        return dict(self.values)

    def save(self, values):
        self.values.update(values)


class EngineeringSettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_modes_and_roi_count_are_validated_and_persisted(self):
        repository = MemorySettingsRepository()
        bus = EventBus()
        events = []
        bus.subscribe(EventType.SETTINGS_CHANGED, events.append)
        service = EngineeringSettingsService(repository, bus)
        self.assertEqual(service.current.peak_detection_method, "mad_mean")
        self.assertEqual(service.current.trend_chart_mode, "bars")
        self.assertEqual(service.current.breathing_identification_method, "model")
        self.assertTrue(service.current.waveform_fill_enabled)
        self.assertEqual(service.current.trend_decimal_places, 0)

        visible_tabs = tuple(tab for tab in INTERFACE_TABS if tab != "trends")
        visible_elements = tuple(
            element
            for element in ALL_INTERFACE_ELEMENTS
            if element not in {"main.trends", "patient.history"}
        )
        saved = service.save(EngineeringSettings(
            work_modes=("adult", "ventilation"),
            roi_count=4,
            peak_detection_method="legacy",
            visible_tabs=visible_tabs,
            show_main_trends=False,
            show_main_tvi=False,
            visible_elements=visible_elements,
            graph_display_period_seconds=90,
            trend_point_mode="breath_cycle",
            trend_downsampling_mode="manual_infant",
            trend_chart_mode="lines",
            peep_silent_threshold_percent=12,
            peep_analysis_interval_seconds=20,
            peep_gravity_angle_degrees=30,
            breathing_identification_method="spectral",
            application_background_color="#123456",
            waveform_fill_enabled=False,
            trend_decimal_places=2,
            hidden_trend_metrics=("eeli_au", "tvi_au", "roi_1_percent"),
            hidden_aeration_metrics=("total_percent", "right_left_ratio"),
        ))
        restored = EngineeringSettingsService(repository, EventBus()).current

        self.assertEqual(saved, restored)
        self.assertEqual(restored.roi_count, 4)
        self.assertEqual(restored.work_modes, ("adult", "ventilation"))
        self.assertEqual(restored.peak_detection_method, "legacy")
        self.assertEqual(restored.graph_display_period_seconds, 90)
        self.assertEqual(restored.trend_point_mode, "breath_cycle")
        self.assertEqual(restored.trend_downsampling_mode, "manual_infant")
        self.assertEqual(restored.trend_chart_mode, "lines")
        self.assertEqual(restored.peep_silent_threshold_percent, 12)
        self.assertEqual(restored.peep_analysis_interval_seconds, 20)
        self.assertEqual(restored.peep_gravity_angle_degrees, 30)
        self.assertEqual(restored.breathing_identification_method, "spectral")
        self.assertEqual(restored.application_background_color, "#123456")
        self.assertFalse(restored.waveform_fill_enabled)
        self.assertEqual(restored.trend_decimal_places, 2)
        self.assertEqual(
            restored.hidden_trend_metrics,
            ("eeli_au", "tvi_au", "roi_1_percent"),
        )
        self.assertEqual(
            restored.hidden_aeration_metrics,
            ("total_percent", "right_left_ratio"),
        )
        self.assertFalse(restored.is_aeration_metric_visible("right_left_ratio"))
        self.assertTrue(restored.is_aeration_metric_visible("tvi_au"))
        self.assertTrue(restored.is_aeration_metric_visible("eili_au"))
        self.assertEqual(restored.visible_tabs, visible_tabs)
        self.assertFalse(restored.show_main_trends)
        self.assertFalse(restored.show_main_tvi)
        self.assertNotIn("patient.history", restored.visible_elements)
        self.assertNotIn("main.trends", restored.visible_elements)
        self.assertEqual(len(events), 1)
        for invalid in (0, 1, 3, 22):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    EngineeringSettings(("adult",), invalid)
        with self.assertRaises(ValueError):
            EngineeringSettings((), 8)
        with self.assertRaises(ValueError):
            EngineeringSettings(visible_tabs=("main",))
        with self.assertRaises(ValueError):
            EngineeringSettings(trend_point_mode="unknown")
        with self.assertRaises(ValueError):
            EngineeringSettings(trend_downsampling_mode="unknown")
        with self.assertRaises(ValueError):
            EngineeringSettings(trend_chart_mode="unknown")
        with self.assertRaises(ValueError):
            EngineeringSettings(breathing_identification_method="unknown")
        with self.assertRaises(ValueError):
            EngineeringSettings(waveform_fill_enabled=1)
        with self.assertRaises(ValueError):
            EngineeringSettings(hidden_trend_metrics=("unknown",))
        with self.assertRaises(ValueError):
            EngineeringSettings(hidden_trend_metrics=("eeli_au", "eeli_au"))
        with self.assertRaises(ValueError):
            EngineeringSettings(hidden_aeration_metrics=("unknown",))
        with self.assertRaises(ValueError):
            EngineeringSettings(
                hidden_aeration_metrics=("total_percent", "total_percent")
            )
        for invalid in (-1, 4, 1.5, True):
            with self.subTest(trend_decimal_places=invalid):
                with self.assertRaises(ValueError):
                    EngineeringSettings(trend_decimal_places=invalid)
        for invalid in (9, 121, 10.5, True):
            with self.subTest(graph_display_period_seconds=invalid):
                with self.assertRaises(ValueError):
                    EngineeringSettings(graph_display_period_seconds=invalid)
        for invalid in ("123456", "#12345", "#xyzxyz", None):
            with self.subTest(application_background_color=invalid):
                with self.assertRaises(ValueError):
                    EngineeringSettings(application_background_color=invalid)

    def test_section_profile_library_and_custom_profile_are_persisted(self):
        repository = MemorySettingsRepository()
        custom = ellipse_profile(
            width_m=0.31,
            height_m=0.22,
            profile_id="custom-wide-v1",
            display_name="Широкий пользовательский",
            left_lung_radius_factors=(1.0,) * 31 + (1.2,),
            right_lung_radius_factors=(0.9,) * 32,
            left_lung_center=(0.36, 0.08),
            right_lung_center=(-0.32, -0.06),
        )
        service = EngineeringSettingsService(repository, EventBus())
        service.save(EngineeringSettings(
            section_profile=custom,
            custom_section_profiles=(custom,),
        ))
        restored = EngineeringSettingsService(repository, EventBus()).current
        self.assertEqual(restored.section_profile, custom)
        self.assertEqual(restored.custom_section_profiles, (custom,))
        self.assertTrue(restored.section_profile.lungs_enabled)
        self.assertEqual(restored.section_profile.left_lung_radius_factors[-1], 1.2)
        self.assertEqual(restored.section_profile.left_lung_center, (0.36, 0.08))
        self.assertEqual(restored.section_profile.right_lung_center, (-0.32, -0.06))

    def test_legacy_section_profile_gets_default_lungs(self):
        payload = EngineeringSettings().to_payload()
        for key in (
            "lungs_enabled",
            "left_lung_radius_factors",
            "right_lung_radius_factors",
            "left_lung_center",
            "right_lung_center",
        ):
            payload["section_profile"].pop(key)

        restored = EngineeringSettings.from_payload(payload)

        self.assertTrue(restored.section_profile.lungs_enabled)
        self.assertEqual(
            restored.section_profile.left_lung_radius_factors,
            (),
        )
        self.assertEqual(
            len(restored.section_profile.lung_radius_factors("left")),
            32,
        )
        self.assertEqual(restored.section_profile.left_lung_center, (0.28, 0.0))
        self.assertEqual(restored.section_profile.right_lung_center, (-0.28, 0.0))

    def test_lung_centers_move_freely_but_remain_inside_section(self):
        profile = ellipse_profile(width_m=0.31, height_m=0.24)
        crossed = profile.with_lung_center("left", (-0.12, 0.08))
        self.assertAlmostEqual(crossed.left_lung_center[0], -0.12)
        self.assertAlmostEqual(crossed.left_lung_center[1], 0.08)

        constrained = crossed.with_lung_center("left", (1.4, 1.4))
        self.assertNotEqual(constrained.left_lung_center, (1.4, 1.4))
        for index in range(32):
            x, y = constrained.lung_point("left", index)
            self.assertLessEqual(
                np.hypot(x, y),
                constrained.radius_at(np.arctan2(y, x)) * 0.995001,
            )

    def test_running_monitor_defers_reconstruction_profile_until_stop(self):
        monitoring = MonitoringService(SimulationDataSource(), EventBus())
        selected = ellipse_profile(
            width_m=0.28,
            height_m=0.19,
            profile_id="deferred-profile-v1",
            display_name="Deferred",
        )
        monitoring.start()
        try:
            self.assertFalse(monitoring.set_section_profile(selected))
            self.assertNotEqual(
                monitoring.section_profile.profile_id, selected.profile_id
            )
        finally:
            monitoring.stop()
        self.assertEqual(monitoring.section_profile.profile_id, selected.profile_id)

    def test_system_information_engineering_tab_prevents_zero_modes(self):
        repository = MemorySettingsRepository()
        service = EngineeringSettingsService(repository, EventBus())
        screen = SystemInfoScreen(engineering_settings=service)
        try:
            self.assertEqual(screen._engineering_sections.tabText(0), "Основные")
            self.assertEqual(screen._engineering_sections.tabText(1), "Тренды")
            self.assertEqual(screen._engineering_sections.tabText(2), "PEEP")
            self.assertEqual(screen._engineering_sections.tabText(3), "Вкладки")
            self.assertEqual(screen._engineering_sections.tabText(4), "Сечение")
            self.assertEqual(screen._engineering_sections.tabText(5), "Внешний вид")
            self.assertEqual(screen._engineering_sections.tabText(6), "Справка")
            margins = screen.layout().contentsMargins()
            self.assertEqual(
                (margins.left(), margins.top(), margins.right(), margins.bottom()),
                (24, 14, 24, 14),
            )
            self.assertEqual(screen.layout().spacing(), 10)
            self.assertIn("font-size:22px", screen._lbl_title.styleSheet())
            self.assertGreaterEqual(screen._section_profile_editor.profile_combo.count(), 4)
            self.assertEqual(screen._element_visibility_tabs.count(), len(INTERFACE_TABS))
            self.assertNotIn("\n", screen._element_visibility_selector.itemText(0))
            self.assertFalse(screen._tab_visibility_checks["main"].isEnabled())
            self.assertFalse(screen._tab_visibility_checks["system"].isEnabled())
            self.assertTrue(screen._element_visibility_checks["main.mvi"].isChecked())
            self.assertTrue(
                screen._element_visibility_checks[
                    "express_monitoring.plethysmogram"
                ].isChecked()
            )
            self.assertTrue(screen._peep_tab_visibility_check.isChecked())
            adult = screen._mode_checks["adult"]
            adult.click()
            self.assertTrue(adult.isChecked())

            screen._mode_checks["infant"].setChecked(True)
            screen._roi_spin.setValue(4)
            self.assertEqual(screen._graph_period_slider.minimum(), 10)
            self.assertEqual(screen._graph_period_slider.maximum(), 120)
            slider_style = screen._graph_period_slider.styleSheet()
            self.assertIn("QSlider#graph_period_slider::groove:horizontal", slider_style)
            self.assertIn("height: 6px", slider_style)
            screen._graph_period_slider.setValue(90)
            self.assertEqual(screen._graph_period_value.text(), "90 с")
            self.assertEqual(screen._selected_background_color, "#0d1117")
            self.assertFalse(screen._background_color_reset.isEnabled())
            self.assertTrue(screen._waveform_fill_check.isChecked())
            self.assertGreaterEqual(screen._waveform_fill_check.minimumHeight(), 48)
            screen._waveform_fill_check.setChecked(False)
            with patch.object(
                QColorDialog,
                "getColor",
                return_value=QColor("#123456"),
            ):
                screen._background_color_button.click()
            self.assertEqual(screen._selected_background_color, "#123456")
            self.assertGreaterEqual(screen._background_color_button.height(), 48)
            self.assertTrue(screen._background_color_reset.isEnabled())
            screen._background_color_reset.click()
            self.assertEqual(screen._selected_background_color, "#0d1117")
            self.assertFalse(screen._background_color_reset.isEnabled())
            screen._set_background_color("#123456")
            screen._peak_detector_combo.setCurrentIndex(
                screen._peak_detector_combo.findData("legacy")
            )
            screen._trend_point_mode_combo.setCurrentIndex(
                screen._trend_point_mode_combo.findData("breath_cycle")
            )
            screen._trend_downsampling_combo.setCurrentIndex(
                screen._trend_downsampling_combo.findData("manual_infant")
            )
            self.assertEqual(screen._trend_chart_mode_combo.currentData(), "bars")
            self.assertEqual(screen._trend_rounding_spin.value(), 0)
            self.assertGreaterEqual(screen._trend_rounding_spin.minimumHeight(), 48)
            screen._trend_rounding_spin.setValue(2)
            for code in ("eeli_au", "tvi_au", "roi_1_percent"):
                screen._trend_visibility_checks[code].setChecked(False)
            for code in ("total_percent", "right_left_ratio"):
                screen._aeration_visibility_checks[code].setChecked(False)
            screen._roi_spin.setValue(4)
            self.assertEqual(len(screen._trend_visibility_checks), 18)
            self.assertEqual(len(screen._aeration_visibility_checks), 19)
            self.assertFalse(
                screen._trend_visibility_checks["roi_1_percent"].isChecked()
            )
            screen._trend_chart_mode_combo.setCurrentIndex(
                screen._trend_chart_mode_combo.findData("lines")
            )
            screen._peep_threshold_spin.setValue(12)
            screen._peep_interval_spin.setValue(20)
            screen._peep_gravity_spin.setValue(30)
            screen._peep_tab_visibility_check.setChecked(False)
            self.assertFalse(
                screen._tab_visibility_checks["peep"].isChecked()
            )
            screen._tab_visibility_checks["trends"].setChecked(False)
            screen._show_main_trends_check.setChecked(False)
            screen._show_main_tvi_check.setChecked(False)
            screen._element_visibility_checks["patient.history"].setChecked(False)
            screen._element_visibility_checks["main.mvi"].setChecked(False)
            self.assertEqual(screen._roi_spin.validate("3", 1)[0], QValidator.Invalid)
            self.assertEqual(screen._roi_spin.validate("20", 2)[0], QValidator.Acceptable)
            screen._engineering_apply.click()
            self.assertEqual(service.current.roi_count, 4)
            self.assertEqual(service.current.work_modes, ("adult", "infant"))
            self.assertEqual(service.current.peak_detection_method, "legacy")
            self.assertEqual(service.current.graph_display_period_seconds, 90)
            self.assertEqual(service.current.trend_point_mode, "breath_cycle")
            self.assertEqual(
                service.current.trend_downsampling_mode, "manual_infant"
            )
            self.assertEqual(service.current.trend_chart_mode, "lines")
            self.assertEqual(service.current.trend_decimal_places, 2)
            self.assertEqual(
                service.current.hidden_trend_metrics,
                ("eeli_au", "tvi_au", "roi_1_percent"),
            )
            self.assertEqual(
                service.current.hidden_aeration_metrics,
                ("total_percent", "right_left_ratio"),
            )
            self.assertEqual(service.current.peep_silent_threshold_percent, 12)
            self.assertEqual(service.current.peep_analysis_interval_seconds, 20)
            self.assertEqual(service.current.peep_gravity_angle_degrees, 30)
            self.assertEqual(service.current.application_background_color, "#123456")
            self.assertFalse(service.current.waveform_fill_enabled)
            self.assertNotIn("peep", service.current.visible_tabs)
            self.assertNotIn("trends", service.current.visible_tabs)
            self.assertFalse(service.current.show_main_trends)
            self.assertFalse(service.current.show_main_tvi)
            self.assertNotIn("patient.history", service.current.visible_elements)
            self.assertNotIn("main.mvi", service.current.visible_elements)
        finally:
            screen.close()

    def test_engineering_reference_is_scrollable_complete_and_retranslated(self):
        previous_language = i18n.lang
        screen = SystemInfoScreen()
        try:
            self.assertEqual(len(screen._reference_rows), 19)
            self.assertEqual(screen._reference_rows[0][3].text(), "С")
            self.assertIn("Событие мониторинга", screen._reference_rows[0][4].text())
            self.assertTrue(
                screen._engineering_reference_tab.findChild(
                    QScrollArea, "engineering_reference_scroll"
                ).widgetResizable()
            )

            i18n.set_language("en")
            self.app.processEvents()
            self.assertEqual(screen._engineering_sections.tabText(6), "Reference")
            self.assertEqual(screen._reference_rows[0][3].text(), "E")
            self.assertIn("Monitoring event", screen._reference_rows[0][4].text())
            self.assertIn("not litres per minute", screen._reference_rows[6][4].text())
            screen._engineering_sections.setCurrentIndex(6)
            self.assertTrue(screen._engineering_apply.isHidden())
            self.assertTrue(screen._section_save.isHidden())
        finally:
            i18n.set_language(previous_language)
            screen.close()

    def test_waveform_panels_apply_fill_preference_to_existing_and_new_rows(self):
        panel = WaveformPanel(roi_count=8)
        regional = RegionalWaveformPanel(roi_count=8)
        try:
            panel.set_fill_enabled(False)
            regional.set_fill_enabled(False)
            panel.set_roi_count(10)
            regional.set_roi_count(10)

            panel_canvases = [
                row.canvas for row in (
                    panel.row_global, panel.row_r_agg, panel.row_l_agg,
                    *panel.rows_r, *panel.rows_l,
                ) if row is not None
            ]
            regional_canvases = [
                row.canvas for row in (
                    regional._col_r.agg, regional._col_l.agg,
                    *regional._col_r.rois, *regional._col_l.rois,
                )
            ]
            self.assertTrue(panel_canvases)
            self.assertTrue(regional_canvases)
            self.assertTrue(all(not canvas._fill_enabled for canvas in panel_canvases))
            self.assertTrue(all(not canvas._fill_enabled for canvas in regional_canvases))
        finally:
            panel.close()
            regional.close()

    def test_trend_value_table_rounding_changes_without_reloading_series(self):
        table = _MetricValueTable((("TVi", "tvi", "a.u."),))
        try:
            table.set_series(
                [np.asarray([1.49, 2.51, -0.49, np.nan])],
                np.asarray([0.0, 15.0, 30.0, 45.0]),
                (0.0, 45.0),
            )
            self.assertEqual(table.item(0, 0).text(), "1")
            self.assertEqual(table.item(0, 1).text(), "3")
            self.assertEqual(table.item(0, 2).text(), "0")
            self.assertEqual(table.item(0, 3).text(), "—")

            table.set_decimal_places(2)
            self.assertEqual(table.item(0, 0).text(), "1.49")
            self.assertEqual(table.item(0, 1).text(), "2.51")
            self.assertEqual(table.item(0, 2).text(), "-0.49")
            self.assertEqual(table.item(0, 3).text(), "—")
        finally:
            table.close()

    def test_section_editor_creates_parametric_custom_profile(self):
        service = EngineeringSettingsService(MemorySettingsRepository(), EventBus())
        screen = SystemInfoScreen(engineering_settings=service)
        try:
            editor = screen._section_profile_editor
            self.assertTrue(editor.lungs_check.isChecked())
            self.assertFalse(editor.width_spin.isEnabled())
            self.assertFalse(editor.name_edit.isEnabled())
            self.assertFalse(editor.canvas.editable)
            self.assertTrue(editor.control_scroll.widgetResizable())
            for combo in (editor.profile_combo, editor.edit_target_combo):
                self.assertGreaterEqual(combo.minimumHeight(), 48)
                self.assertIn("QAbstractItemView", combo.view().styleSheet())
                self.assertEqual(
                    combo.view().palette().color(QPalette.Base).name(),
                    "#111827",
                )
                self.assertEqual(
                    combo.view().palette().color(QPalette.Text).name(),
                    "#e8eaed",
                )
                self.assertGreaterEqual(
                    combo.itemDelegate().sizeHint(
                        QStyleOptionViewItem(), combo.model().index(0, 0)
                    ).height(),
                    48,
                )
            self.assertGreaterEqual(editor.width_spin.height(), 42)
            self.assertFalse(screen._section_save.isEnabled())
            self.assertTrue(screen._engineering_apply.isEnabled())
            editor.copy_button.click()
            self.assertTrue(editor.width_spin.isEnabled())
            self.assertTrue(editor.canvas.editable)
            self.assertTrue(screen._section_save.isEnabled())
            self.assertFalse(screen._engineering_apply.isEnabled())
            self.assertTrue(editor.lungs_check.isEnabled())
            editor.lungs_check.setChecked(False)
            self.assertFalse(editor._active.lungs_enabled)
            editor.undo_button.click()
            self.assertTrue(editor._active.lungs_enabled)
            editor.redo_button.click()
            self.assertFalse(editor._active.lungs_enabled)
            editor.undo_button.click()
            self.assertTrue(editor._active.lungs_enabled)
            self.assertEqual(
                screen._engineering_apply.toolTip(),
                "Сначала сохраните изменения модели сечения",
            )
            editor.name_edit.setText("Широкое сечение")
            editor.width_spin.setValue(315.0)
            editor.height_spin.setValue(225.0)
            editor.rotation_spin.setValue(12.0)
            editor.edit_target_combo.setCurrentIndex(
                editor.edit_target_combo.findData("left")
            )
            before_lung = editor._active.lung_radius_factors("left")
            point_x, point_y = editor.canvas._lung_screen_point("left", 0)
            editor.canvas._edit_at(point_x - 12.0, point_y)
            editor._finish_radial_edit(editor.canvas.profile)
            self.assertNotEqual(
                editor._active.lung_radius_factors("left"), before_lung
            )
            self.assertTrue(editor.undo_button.isEnabled())
            self.assertFalse(editor.redo_button.isEnabled())
            editor.undo_button.click()
            self.assertEqual(editor._active.lung_radius_factors("left"), before_lung)
            self.assertTrue(editor.redo_button.isEnabled())
            editor.redo_button.click()
            self.assertNotEqual(
                editor._active.lung_radius_factors("left"), before_lung
            )
            editor.edit_target_combo.setCurrentIndex(0)
            editor.undo_button.click()
            self.assertEqual(editor._active.lung_radius_factors("left"), before_lung)
            editor.undo_button.click()
            self.assertNotAlmostEqual(editor.rotation_spin.value(), 12.0)
            editor.redo_button.click()
            self.assertAlmostEqual(editor.rotation_spin.value(), 12.0)
            screen._section_save.click()
            self.assertFalse(screen._section_save.isEnabled())
            self.assertTrue(screen._engineering_apply.isEnabled())
            self.assertEqual(screen._engineering_apply.toolTip(), "")
            self.assertNotAlmostEqual(service.current.section_profile.width_m, 0.315)
            editor.name_edit.setText("")
            self.assertFalse(screen._section_save.isEnabled())
            self.assertFalse(screen._engineering_apply.isEnabled())
            editor.reset_button.click()
            self.assertEqual(editor.name_edit.text(), "Широкое сечение")
            editor.name_edit.setText("Временное название")
            editor.undo_button.click()
            self.assertEqual(editor.name_edit.text(), "Широкое сечение")
            editor.redo_button.click()
            self.assertEqual(editor.name_edit.text(), "Временное название")
            editor.reset_button.click()
            self.assertEqual(editor.name_edit.text(), "Широкое сечение")
            editor.smooth_button.click()
            self.assertEqual(editor._active.shape_kind, "radial")
            editor.undo_button.click()
            self.assertEqual(editor._active.shape_kind, "ellipse")
            editor.redo_button.click()
            self.assertEqual(editor._active.shape_kind, "radial")
            editor.reset_button.click()
            self.assertEqual(editor._active.shape_kind, "ellipse")
            editor.width_spin.setValue(330.0)
            self.assertTrue(editor.reset_button.isEnabled())
            editor.reset_button.click()
            self.assertAlmostEqual(editor.width_spin.value(), 315.0)
            screen._engineering_apply.click()
            profile = service.current.section_profile
            self.assertEqual(profile.shape_kind, "ellipse")
            self.assertEqual(profile.display_name, "Широкое сечение")
            self.assertAlmostEqual(profile.width_m, 0.315)
            self.assertAlmostEqual(profile.height_m, 0.225)
            self.assertAlmostEqual(profile.rotation_degrees, 12.0)
            self.assertIn(profile, service.current.custom_section_profiles)
        finally:
            screen.close()

    def test_section_editor_dropdown_popup_is_readable_and_selectable(self):
        editor = SectionProfileEditor()
        try:
            editor.resize(1000, 700)
            editor.show()
            editor.copy_button.click()
            self.app.processEvents()

            combo = editor.edit_target_combo
            combo.showPopup()
            self.app.processEvents()
            left_index = combo.model().index(combo.findData("left"), 0)
            left_rect = combo.view().visualRect(left_index)
            self.assertGreaterEqual(left_rect.height(), 48)
            QTest.mouseClick(
                combo.view().viewport(), Qt.LeftButton, pos=left_rect.center()
            )
            self.app.processEvents()

            self.assertEqual(combo.currentData(), "left")
            self.assertEqual(editor.canvas.edit_target, "left")
        finally:
            editor.close()

    def test_section_editor_drags_lung_interior_and_undoes_translation(self):
        editor = SectionProfileEditor()
        try:
            editor.resize(1000, 700)
            editor.show()
            editor.copy_button.click()
            editor.edit_target_combo.setCurrentIndex(
                editor.edit_target_combo.findData("left")
            )
            self.app.processEvents()

            canvas = editor.canvas
            before_center = editor._active.left_lung_center
            before_shape = editor._active.lung_radius_factors("left")
            cx, cy, scale = canvas._center_and_scale()
            start = QPoint(
                round(cx - before_center[0] * editor._active.radius_m * scale),
                round(cy - before_center[1] * editor._active.radius_m * scale),
            )
            finish = start + QPoint(-35, -20)
            QTest.mousePress(canvas, Qt.LeftButton, pos=start)
            QTest.mouseMove(canvas, finish)
            QTest.mouseRelease(canvas, Qt.LeftButton, pos=finish)
            self.app.processEvents()

            moved_center = editor._active.left_lung_center
            self.assertGreater(moved_center[0], before_center[0])
            self.assertGreater(moved_center[1], before_center[1])
            self.assertEqual(editor._active.lung_radius_factors("left"), before_shape)
            editor.undo_button.click()
            self.assertEqual(editor._active.left_lung_center, before_center)
        finally:
            editor.close()

    def test_existing_visibility_settings_migrate_peep_to_navigation(self):
        old_payload = EngineeringSettings().to_payload()
        old_payload["interface_elements_version"] = 1
        old_payload.pop("trend_chart_mode")
        old_payload.pop("waveform_fill_enabled")
        old_payload.pop("trend_decimal_places")
        old_payload["visible_tabs"].remove("peep")
        old_payload["visible_elements"] = [
            element
            for element in old_payload["visible_elements"]
            if element not in {"main.mvi", "main.velocity", *INTERFACE_ELEMENTS["peep"]}
        ]
        old_payload["visible_elements"].append("analysis.peep_tab")
        service = EngineeringSettingsService(
            MemorySettingsRepository({"engineering_settings": old_payload}),
            EventBus(),
        )

        self.assertIn("main.mvi", service.current.visible_elements)
        self.assertIn("main.velocity", service.current.visible_elements)
        self.assertIn("peep", service.current.visible_tabs)
        self.assertTrue(
            set(INTERFACE_ELEMENTS["peep"]).issubset(service.current.visible_elements)
        )
        self.assertNotIn("analysis.peep_tab", service.current.visible_elements)
        self.assertEqual(service.current.trend_chart_mode, "bars")
        self.assertTrue(service.current.waveform_fill_enabled)
        self.assertEqual(service.current.trend_decimal_places, 0)

    def test_four_roi_metrics_and_waveform_panels_use_four_regions(self):
        fs = 25.0
        time = np.arange(0.0, 20.0, 1.0 / fs)
        breathing = 10.0 + 2.0 * np.sin(2.0 * np.pi * 0.25 * time)
        weights = (3.0, 1.0, 3.0, 1.0)
        rois = [breathing * weight / sum(weights) for weight in weights]
        result = calculate_aeration_metrics(
            breathing,
            rois,
            AerationAlgorithmParameters(sample_rate_hz=fs, roi_count=4),
        )

        self.assertEqual(len(result.roi_percent), 4)
        self.assertAlmostEqual(result.right_percent, 50.0)
        self.assertAlmostEqual(result.left_percent, 50.0)

        main = WaveformPanel(roi_count=8)
        regional = RegionalWaveformPanel(roi_count=8)
        try:
            main.set_roi_count(4)
            regional.set_roi_count(4)
            self.assertEqual(len(main.rows_r), 2)
            self.assertEqual(len(main.rows_l), 2)
            self.assertEqual(len(regional._col_r.rois), 2)
            self.assertEqual(len(regional._col_l.rois), 2)
            main.set_roi_count(20)
            regional.set_roi_count(20)
            self.assertEqual(len(main.rows_r), 10)
            self.assertEqual(len(main.rows_l), 10)
            self.assertEqual(len(regional._col_r.rois), 10)
            self.assertEqual(len(regional._col_l.rois), 10)
        finally:
            main.close()
            regional.close()

    def test_monitoring_pipeline_switches_to_configured_roi_count(self):
        monitoring = MonitoringService(
            SimulationDataSource(seed=7, playback_speed=100.0),
            EventBus(),
            buffer_seconds=5,
        )
        try:
            monitoring.set_roi_count(4)
            monitoring.set_aeration_configuration(
                roi_count=4, peak_detection_method="legacy"
            )
            monitoring.start()
            monitoring.prime(75)
            view = monitoring.read_view(2.0)
            self.assertEqual(len(view.waveforms["rois"]), 4)
            self.assertEqual(len(view.snapshot.roi_pct), 4)
            self.assertEqual(view.snapshot.algorithm_parameters.roi_count, 4)
            self.assertEqual(
                view.snapshot.algorithm_parameters.peak_detection_method, "legacy"
            )
        finally:
            monitoring.stop()


if __name__ == "__main__":
    unittest.main()
