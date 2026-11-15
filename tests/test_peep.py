import os
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.application import PeepProcessor, calculate_peep_metrics
from app.application.monitoring import MonitoringSnapshot
from app.screens.analysis_screen import PeepTab


class PeepCalculationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _lung_coordinates(shape=(64, 64)):
        height, width = shape
        y, x = np.mgrid[-1.0:1.0:complex(height), -1.0:1.0:complex(width)]
        mask = (
            (((x + 0.34) / 0.34) ** 2 + (y / 0.62) ** 2 <= 1.0)
            | (((x - 0.34) / 0.34) ** 2 + (y / 0.62) ** 2 <= 1.0)
        )
        return y, x, mask

    def test_homogeneous_ventilation_is_all_functional(self):
        _, _, lung = self._lung_coordinates()
        tidal = np.zeros((64, 64), dtype=float)
        tidal[lung] = 1.0

        result = calculate_peep_metrics(tidal)

        self.assertTrue(result.available)
        self.assertAlmostEqual(result.fls_percent, 100.0)
        self.assertAlmostEqual(result.dss_percent, 0.0)
        self.assertAlmostEqual(result.nss_percent, 0.0)
        self.assertAlmostEqual(result.cov_v_percent, 50.0, delta=1.0)
        self.assertAlmostEqual(result.cov_h_percent, 50.0, delta=1.0)
        self.assertIsNotNone(result.horizon_line)

    def test_upper_silent_space_is_nss_and_percentages_total_100(self):
        y, _, lung = self._lung_coordinates()
        tidal = np.zeros((64, 64), dtype=float)
        tidal[lung] = 1.0
        tidal[lung & (y < 0)] = 0.05

        result = calculate_peep_metrics(tidal, silent_threshold_percent=10)

        self.assertTrue(result.available)
        self.assertGreater(result.nss_percent, 45.0)
        self.assertLess(result.dss_percent, 1.0)
        self.assertGreater(result.cov_v_percent, 60.0)
        self.assertAlmostEqual(
            result.fls_percent + result.dss_percent + result.nss_percent,
            100.0,
            places=9,
        )

    def test_processor_uses_minimum_and_maximum_global_frames(self):
        _, _, lung = self._lung_coordinates()
        low = np.zeros((64, 64), dtype=float)
        high = np.zeros((64, 64), dtype=float)
        high[lung] = 2.0
        processor = PeepProcessor(sample_rate_hz=1.0, analysis_interval_seconds=5)
        processor.process(low, 0.0)
        processor.process(high, 10.0)

        result = processor.result()

        self.assertTrue(result.available)
        self.assertEqual(result.analyzed_sample_count, 2)
        self.assertAlmostEqual(result.fls_percent, 100.0)

    def test_tab_displays_manual_parameter_names(self):
        tab = PeepTab()
        try:
            tab.update_data(MonitoringSnapshot(), {})
            labels = [label.text() for label in tab.findChildren(type(tab._details))]
            joined = " ".join(labels)
            for code in ("FLS", "DSS", "NSS", "CoV(v)", "CoV(h)", "HoV"):
                self.assertIn(code, joined)
        finally:
            tab.close()


if __name__ == "__main__":
    unittest.main()
