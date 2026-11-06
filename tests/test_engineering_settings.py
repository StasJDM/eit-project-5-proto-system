import os
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QValidator

from app.application import (
    AerationAlgorithmParameters,
    EngineeringSettings,
    EngineeringSettingsService,
    EventBus,
    EventType,
    MonitoringService,
    calculate_aeration_metrics,
)
from app.data_sources import SimulationDataSource
from app.screens.system_info_screen import SystemInfoScreen
from app.widgets.waveform_panel import RegionalWaveformPanel, WaveformPanel


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

        saved = service.save(EngineeringSettings(
            ("adult", "ventilation"), 4, "legacy"
        ))
        restored = EngineeringSettingsService(repository, EventBus()).current

        self.assertEqual(saved, restored)
        self.assertEqual(restored.roi_count, 4)
        self.assertEqual(restored.work_modes, ("adult", "ventilation"))
        self.assertEqual(restored.peak_detection_method, "legacy")
        self.assertEqual(len(events), 1)
        for invalid in (0, 1, 3, 22):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    EngineeringSettings(("adult",), invalid)
        with self.assertRaises(ValueError):
            EngineeringSettings((), 8)

    def test_system_information_engineering_tab_prevents_zero_modes(self):
        repository = MemorySettingsRepository()
        service = EngineeringSettingsService(repository, EventBus())
        screen = SystemInfoScreen(engineering_settings=service)
        try:
            adult = screen._mode_checks["adult"]
            adult.click()
            self.assertTrue(adult.isChecked())

            screen._mode_checks["infant"].setChecked(True)
            screen._roi_spin.setValue(4)
            screen._peak_detector_combo.setCurrentIndex(
                screen._peak_detector_combo.findData("legacy")
            )
            self.assertEqual(screen._roi_spin.validate("3", 1)[0], QValidator.Invalid)
            self.assertEqual(screen._roi_spin.validate("20", 2)[0], QValidator.Acceptable)
            screen._engineering_apply.click()
            self.assertEqual(service.current.roi_count, 4)
            self.assertEqual(service.current.work_modes, ("adult", "infant"))
            self.assertEqual(service.current.peak_detection_method, "legacy")
        finally:
            screen.close()

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
