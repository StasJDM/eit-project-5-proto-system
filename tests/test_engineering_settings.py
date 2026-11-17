import os
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QValidator

from app.application import (
    ALL_INTERFACE_ELEMENTS,
    AerationAlgorithmParameters,
    EngineeringSettings,
    EngineeringSettingsService,
    EventBus,
    EventType,
    INTERFACE_TABS,
    MonitoringService,
    calculate_aeration_metrics,
)
from app.data_sources import SimulationDataSource
from app.screens.system_info_screen import SystemInfoScreen
from app.widgets.waveform_panel import RegionalWaveformPanel, WaveformPanel
from app.reconstruction import ellipse_profile


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
        for invalid in (9, 121, 10.5, True):
            with self.subTest(graph_display_period_seconds=invalid):
                with self.assertRaises(ValueError):
                    EngineeringSettings(graph_display_period_seconds=invalid)

    def test_section_profile_library_and_custom_profile_are_persisted(self):
        repository = MemorySettingsRepository()
        custom = ellipse_profile(
            width_m=0.31,
            height_m=0.22,
            profile_id="custom-wide-v1",
            display_name="Широкий пользовательский",
        )
        service = EngineeringSettingsService(repository, EventBus())
        service.save(EngineeringSettings(
            section_profile=custom,
            custom_section_profiles=(custom,),
        ))
        restored = EngineeringSettingsService(repository, EventBus()).current
        self.assertEqual(restored.section_profile, custom)
        self.assertEqual(restored.custom_section_profiles, (custom,))

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
            self.assertGreaterEqual(screen._section_profile_editor.profile_combo.count(), 4)
            self.assertEqual(screen._element_visibility_tabs.count(), len(INTERFACE_TABS))
            self.assertNotIn("\n", screen._element_visibility_selector.itemText(0))
            self.assertFalse(screen._tab_visibility_checks["main"].isEnabled())
            self.assertFalse(screen._tab_visibility_checks["system"].isEnabled())
            self.assertTrue(screen._element_visibility_checks["main.mvi"].isChecked())
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
            screen._trend_chart_mode_combo.setCurrentIndex(
                screen._trend_chart_mode_combo.findData("lines")
            )
            screen._peep_threshold_spin.setValue(12)
            screen._peep_interval_spin.setValue(20)
            screen._peep_gravity_spin.setValue(30)
            screen._peep_tab_visibility_check.setChecked(False)
            self.assertFalse(
                screen._element_visibility_checks["analysis.peep_tab"].isChecked()
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
            self.assertEqual(service.current.peep_silent_threshold_percent, 12)
            self.assertEqual(service.current.peep_analysis_interval_seconds, 20)
            self.assertEqual(service.current.peep_gravity_angle_degrees, 30)
            self.assertNotIn("analysis.peep_tab", service.current.visible_elements)
            self.assertNotIn("trends", service.current.visible_tabs)
            self.assertFalse(service.current.show_main_trends)
            self.assertFalse(service.current.show_main_tvi)
            self.assertNotIn("patient.history", service.current.visible_elements)
            self.assertNotIn("main.mvi", service.current.visible_elements)
        finally:
            screen.close()

    def test_section_editor_creates_parametric_custom_profile(self):
        service = EngineeringSettingsService(MemorySettingsRepository(), EventBus())
        screen = SystemInfoScreen(engineering_settings=service)
        try:
            editor = screen._section_profile_editor
            self.assertFalse(editor.width_spin.isEnabled())
            self.assertFalse(editor.name_edit.isEnabled())
            self.assertFalse(editor.canvas.editable)
            self.assertTrue(editor.control_scroll.widgetResizable())
            self.assertGreaterEqual(editor.width_spin.height(), 42)
            self.assertFalse(screen._section_save.isEnabled())
            self.assertTrue(screen._engineering_apply.isEnabled())
            editor.copy_button.click()
            self.assertTrue(editor.width_spin.isEnabled())
            self.assertTrue(editor.canvas.editable)
            self.assertTrue(screen._section_save.isEnabled())
            self.assertFalse(screen._engineering_apply.isEnabled())
            self.assertEqual(
                screen._engineering_apply.toolTip(),
                "Сначала сохраните изменения модели сечения",
            )
            editor.name_edit.setText("Широкое сечение")
            editor.width_spin.setValue(315.0)
            editor.height_spin.setValue(225.0)
            editor.rotation_spin.setValue(12.0)
            self.assertTrue(editor.undo_button.isEnabled())
            self.assertFalse(editor.redo_button.isEnabled())
            editor.undo_button.click()
            self.assertNotAlmostEqual(editor.rotation_spin.value(), 12.0)
            self.assertTrue(editor.redo_button.isEnabled())
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

    def test_existing_visibility_settings_enable_new_mvi_block_during_migration(self):
        old_payload = EngineeringSettings().to_payload()
        old_payload.pop("interface_elements_version")
        old_payload.pop("trend_chart_mode")
        old_payload["visible_elements"] = [
            element
            for element in old_payload["visible_elements"]
            if element not in {"main.mvi", "main.velocity", "analysis.peep_tab"}
        ]
        service = EngineeringSettingsService(
            MemorySettingsRepository({"engineering_settings": old_payload}),
            EventBus(),
        )

        self.assertIn("main.mvi", service.current.visible_elements)
        self.assertIn("main.velocity", service.current.visible_elements)
        self.assertIn("analysis.peep_tab", service.current.visible_elements)
        self.assertEqual(service.current.trend_chart_mode, "bars")

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
