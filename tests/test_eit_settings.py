import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from app.application import EITSettingsService, EventBus, StudyLifecycleService
from app.color_maps import COLOR_MAPS, CUSTOM_COLOR_MAP_ID
from app.config import DataMode
from app.domain import AcquisitionSettings, Patient
from app.screens.eit_settings_screen import EITSettingsScreen
from app.widgets.lung_viz import LungVizWidget
from app.storage import Database, RepositoryBundle


class EITSettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "settings.sqlite3"
        self.database = Database(self.path, DataMode.SIMULATION)
        self.repositories = RepositoryBundle.build(self.database)
        self.bus = EventBus()
        self.service = EITSettingsService(self.repositories.settings, self.bus)

    def tearDown(self):
        self.database.close()
        self.temp.cleanup()

    def test_validated_settings_persist_after_database_reopen(self):
        expected = AcquisitionSettings(
            injection_current_ma=2.5,
            injection_frequency_khz=150.0,
            electrode_count=16,
            belt_count=1,
            electrode_order="sternum_cw",
            measurement_sequence="adjacent_rotating",
            two_color_visualization=False,
            pathology_detection=False,
        )
        self.service.save(expected)
        self.database.close()

        self.database = Database(self.path, DataMode.SIMULATION)
        restored = EITSettingsService(
            RepositoryBundle.build(self.database).settings,
            EventBus(),
        )
        self.assertEqual(restored.current, expected)

    def test_model_rejects_values_outside_declared_limits(self):
        invalid = (
            {"injection_current_ma": 0.4},
            {"injection_frequency_khz": 501.0},
            {"electrode_count": 15},
            {"belt_count": 0},
            {"electrode_order": "unknown"},
            {"measurement_sequence": "unknown"},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                AcquisitionSettings(**values)

    def test_study_captures_saved_snapshot_and_applies_it_when_prepared(self):
        saved = self.service.save(AcquisitionSettings(
            injection_current_ma=3.0,
            injection_frequency_khz=250.0,
        ))
        patient = Patient(external_id="TASK-13")
        self.repositories.patients.save(patient)
        applied = []
        lifecycle = StudyLifecycleService(
            self.repositories.patients,
            self.repositories.studies,
            self.repositories.sessions,
            self.repositories.settings,
            self.bus,
            simulated=True,
            settings_provider=lambda: self.service.current,
            settings_applier=applied.append,
        )
        lifecycle.select_patient(patient.id)
        study = lifecycle.create_study()
        self.service.save(AcquisitionSettings(injection_current_ma=1.5))

        lifecycle.prepare()

        self.assertEqual(study.settings, saved)
        self.assertEqual(applied, [saved])
        self.assertEqual(self.repositories.studies.get(study.id).settings, saved)

    def test_screen_restores_persisted_values_and_confirmed_reset(self):
        self.service.save(AcquisitionSettings(
            injection_current_ma=4.0,
            injection_frequency_khz=300.0,
            electrode_order="sternum_ccw",
            measurement_sequence="adjacent_reciprocal",
            two_color_visualization=False,
        ))
        screen = EITSettingsScreen(settings_service=self.service)
        try:
            self.assertEqual(screen._settings_from_controls(), self.service.current)
            with patch.object(QMessageBox, "exec", return_value=QMessageBox.No):
                screen._reset()
            self.assertEqual(self.service.current.injection_current_ma, 4.0)
            with patch.object(QMessageBox, "exec", return_value=QMessageBox.Yes):
                screen._reset()
            self.assertEqual(self.service.current, AcquisitionSettings())
            self.assertEqual(screen._settings_from_controls(), AcquisitionSettings())
        finally:
            screen.close()

    def test_protocol_hypothesis_dropdowns_are_hidden_from_operator(self):
        screen = EITSettingsScreen(settings_service=self.service)
        try:
            self.assertTrue(screen._row_electrode_order.isHidden())
            self.assertTrue(screen._row_measurement_sequence.isHidden())
            self.assertEqual(screen._settings_from_controls(), self.service.current)
        finally:
            screen.close()

    def test_color_mode_palette_and_custom_colors_are_persisted(self):
        expected = AcquisitionSettings(
            two_color_visualization=False,
            color_map_id=CUSTOM_COLOR_MAP_ID,
            custom_color_low="#123456",
            custom_color_high="#fedcba",
        )
        self.service.save(expected)
        self.database.close()
        self.database = Database(self.path, DataMode.SIMULATION)
        restored = EITSettingsService(
            RepositoryBundle.build(self.database).settings, EventBus()
        )
        self.assertEqual(restored.current, expected)

        screen = EITSettingsScreen(settings_service=restored)
        try:
            self.assertEqual(len(COLOR_MAPS), 15)
            self.assertEqual(screen._color_map._combo.count(), 16)
            self.assertEqual(screen._settings_from_controls(), expected)
            screen._grp_color._btn_a.click()
            self.assertTrue(screen._settings_from_controls().two_color_visualization)
            screen._grp_color._btn_b.click()
            self.assertFalse(screen._settings_from_controls().two_color_visualization)
        finally:
            screen.close()

    def test_lung_map_visibly_applies_one_and_two_color_modes(self):
        widget = LungVizWidget()
        try:
            widget._display_mode = "delta"
            widget._color_limit = 1.0
            widget.set_color_settings(
                two_color=True,
                color_map_id=CUSTOM_COLOR_MAP_ID,
                custom_low="#1122aa",
                custom_high="#ee3300",
            )
            self.assertEqual(widget._element_color(-1.0).name(), "#1122aa")
            self.assertEqual(widget._element_color(1.0).name(), "#ee3300")

            widget.set_color_settings(
                two_color=False,
                color_map_id=CUSTOM_COLOR_MAP_ID,
                custom_low="#1122aa",
                custom_high="#ee3300",
            )
            self.assertEqual(
                widget._element_color(-1.0).name(),
                widget._element_color(1.0).name(),
            )
            self.assertEqual(widget._element_color(1.0).name(), "#ee3300")
        finally:
            widget.close()


if __name__ == "__main__":
    unittest.main()
