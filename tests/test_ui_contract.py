import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("EIT_DATA_MODE", "simulation")
os.environ.setdefault("EIT_DATABASE_PATH", ":memory:")
os.environ.setdefault("EIT_RAW_DATA_DIR", "/tmp/eit-test-frames")
os.environ.setdefault("EIT_EXPORT_DIR", "/tmp/eit-test-exports")

from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QMessageBox
from PySide6.QtTest import QTest

from app.main_window import MainWindow
from app.domain import CalibrationStatus, Patient
from app.application import MonitoringSnapshot
from app.i18n import LANGUAGES, STRINGS, i18n
from app.screens.eit_settings_screen import EITSettingsScreen
from app.screens.main_screen import LeftPanel
from app.ui_text import quality_reason_text, study_conclusion_text, study_status_text


class UiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_navigation_and_window_geometry_remain_unchanged(self):
        window = MainWindow()
        try:
            self.assertEqual(window.minimumWidth(), 1280)
            self.assertEqual(window.minimumHeight(), 768)
            self.assertEqual(
                set(window._screens),
                {
                    "main",
                    "patient",
                    "eit_settings",
                    "trends",
                    "analysis",
                    "reports",
                    "export",
                    "system",
                    "service",
                    "debug",
                },
            )
        finally:
            window.close()

    def test_existing_eit_defaults_stay_at_one_belt_and_16_electrodes(self):
        screen = EITSettingsScreen()
        try:
            values = {field.text() for field in screen.findChildren(QLineEdit)}
            self.assertIn("1", values)
            self.assertIn("16", values)
        finally:
            screen.close()

    def test_unavailable_metrics_are_rendered_as_dash_instead_of_zero(self):
        panel = LeftPanel()
        try:
            panel.update_params(MonitoringSnapshot())
            for box in (
                panel.box_t, panel.box_r, panel.box_l, panel.box_lr,
                panel.box_vd, panel.box_tvi, panel.box_eeli, panel.box_eili,
            ):
                self.assertEqual(box._lbl_val.text(), "—")
                self.assertEqual(box.toolTip(), "Причина: недостаточно данных")
                self.assertNotIn("insufficient_data", box.toolTip())
        finally:
            panel.close()

    def test_ui_domain_codes_are_localized_in_every_supported_language(self):
        previous_language = i18n.lang
        expected_reason = {
            "ru": "недостаточно данных",
            "en": "insufficient data",
            "zh": "数据不足",
            "vi": "không đủ dữ liệu",
        }
        try:
            for language in LANGUAGES:
                with self.subTest(language=language):
                    i18n.set_language(language)
                    self.assertEqual(
                        quality_reason_text("insufficient_data"),
                        expected_reason[language],
                    )
                    self.assertNotEqual(study_status_text("completed"), "completed")
                    self.assertNotEqual(
                        study_conclusion_text("application_closed"),
                        "application_closed",
                    )
        finally:
            i18n.set_language(previous_language)

    def test_every_interface_string_has_all_supported_languages(self):
        for key, translations in STRINGS.items():
            with self.subTest(key=key):
                self.assertEqual(set(translations), set(LANGUAGES))
                self.assertTrue(all(value.strip() for value in translations.values()))

    def test_approved_ratio_label_is_right_over_left(self):
        window = MainWindow()
        try:
            labels = {
                label.text()
                for label in window.findChildren(QLabel)
            }
            self.assertIn("R/L", labels)
            self.assertNotIn("L/R", labels)
        finally:
            window.close()

    def test_system_information_uses_existing_device_row_for_active_mode(self):
        window = MainWindow()
        try:
            labels = {label.text() for label in window.findChildren(QLabel)}
            self.assertIn("Симуляция", labels)
        finally:
            window.close()

    def test_all_start_buttons_follow_one_current_study(self):
        window = MainWindow()
        try:
            patient = Patient(external_id="P-UI-LIFECYCLE")
            window._container.repositories.patients.save(patient)
            lifecycle = window._container.study_lifecycle
            lifecycle.select_patient(patient.id)
            lifecycle.create_study()
            lifecycle.prepare()
            self.app.processEvents()
            self.assertTrue(all(button.isEnabled() for button in window._study_buttons))

            window._study_buttons[-1].click()
            self.app.processEvents()
            self.assertTrue(all(button.text() == "⏹  СТОП" for button in window._study_buttons))
            self.assertTrue(window._container.monitoring_controller.is_running)

            with patch(
                "app.main_window.QMessageBox.exec",
                return_value=QMessageBox.Yes,
            ):
                window._study_buttons[0].click()
            self.app.processEvents()
            self.assertTrue(all(not button.isEnabled() for button in window._study_buttons))
        finally:
            window.close()

    def test_patient_history_row_opens_completed_study_details(self):
        window = MainWindow()
        try:
            patient = Patient(external_id="P-UI-HISTORY")
            window._container.repositories.patients.save(patient)
            lifecycle = window._container.study_lifecycle
            lifecycle.select_patient(patient.id)
            study = lifecycle.create_study(author="ui-operator")
            lifecycle.prepare()
            lifecycle.start()
            lifecycle.stop(conclusion="Stable")
            screen = window._screens["patient"]
            screen.load_patient(patient)
            self.assertEqual(len(screen._history_rows), 1)
            with patch("app.screens.patient_screen.QMessageBox.information") as info:
                screen._history_rows[0]._btn.click()
                info.assert_called_once()
            self.assertEqual(lifecycle.current_study.id, study.id)
            self.assertEqual(lifecycle.current_study.status.value, "completed")
        finally:
            window.close()

    def test_patient_screen_imports_external_eit_json_as_read_only_playback(self):
        path = Path(
            "/Users/stas/my/eit/eit_project_6_air/measurments/sample_sitting.json"
        )
        if not path.is_file():
            self.skipTest("provided sibling JSON fixture is not installed")
        window = MainWindow()
        try:
            screen = window._screens["patient"]
            with patch(
                "app.screens.patient_screen.QFileDialog.getOpenFileName",
                return_value=(str(path), ""),
            ):
                screen._btn_import_json.click()
            self.assertTrue(window._container.playback_service.snapshot.active)
            self.assertTrue(window._container.playback_service.snapshot.read_only)
            self.assertEqual(window._container.monitoring.source.path, path.resolve())
        finally:
            window.close()

    def test_debug_screen_calibrates_and_persists_current_study(self):
        window = MainWindow()
        try:
            patient = Patient(external_id="P-UI-CALIBRATION")
            window._container.repositories.patients.save(patient)
            lifecycle = window._container.study_lifecycle
            lifecycle.select_patient(patient.id)
            study = lifecycle.create_study()
            lifecycle.prepare()
            window._container.data_source.electrode_contact_levels = lambda: (0.9,) * 16
            screen = window._screens["debug"]

            screen._btn_calibrate.click()
            QTest.qWait(300)
            self.app.processEvents()

            restored = window._container.repositories.studies.get(study.id)
            self.assertIsNotNone(restored.calibration)
            self.assertEqual(restored.calibration.status, CalibrationStatus.SUCCEEDED)
            self.assertIn("сохранена", screen._quality_status.text())
        finally:
            window.close()

    def test_event_marker_buttons_journal_and_timelines_share_persisted_marker(self):
        window = MainWindow()
        try:
            self.assertEqual(len(window._marker_buttons), 5)
            self.assertTrue(all(not button.isEnabled() for button in window._marker_buttons))
            patient = Patient(external_id="P-UI-MARKER")
            window._container.repositories.patients.save(patient)
            lifecycle = window._container.study_lifecycle
            lifecycle.select_patient(patient.id)
            lifecycle.create_study(author="ui-doctor")
            lifecycle.prepare()
            window._container.monitoring_controller.start()
            window._sync_study_controls()
            self.assertTrue(all(button.isEnabled() for button in window._marker_buttons))

            QTest.qWait(250)
            marker = window._container.marker_service.create(
                "cough", "Кашель во время мониторинга", "ui-doctor"
            )
            QTest.qWait(100)
            main = window._screens["main"]
            main._on_paint()
            self.assertTrue(main.waves.row_global.canvas._markers)

            trends = window._screens["trends"]
            trends._refresh()
            self.assertTrue(trends.tab_global.left.wave._markers)

            journal = window._screens["service"]
            journal.refresh()
            self.assertEqual(journal._events[0]["event"], marker)
            self.assertIn("ui-doctor", journal._events[0]["desc"])
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
