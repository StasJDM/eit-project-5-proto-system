import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from app.i18n import LANGUAGES, i18n, t
from app.screens.analysis_screen import PathologyTab
from app.screens.debug_screen import _BarChart as DebugBarChart
from app.screens.signal_quality_screen import _BarChart as QualityBarChart
from app.screens.trends_screen import _MultiWave
from app.widgets.chart_zoom import attach_chart_zoom
from app.widgets.waveform_panel import RegionalWaveformPanel, WaveformPanel


class ChartZoomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_touch_magnifier_opens_and_controls_live_zoom(self):
        host = QWidget()
        host.resize(640, 480)
        chart = QWidget(host)
        chart.setGeometry(20, 20, 320, 180)
        host.show()
        controller = attach_chart_zoom(chart)
        self.app.processEvents()
        try:
            self.assertEqual(controller.button.size().width(), 46)
            self.assertEqual(controller.button.size().height(), 46)
            self.assertEqual(controller.button.x(), chart.width() - 52)
            self.assertEqual(controller.button.accessibleName(), t("chart_magnifier"))

            QTest.mouseClick(controller.button, Qt.LeftButton)
            self.app.processEvents()
            overlay = controller.overlay
            self.assertIsNotNone(overlay)
            self.assertEqual(overlay.geometry(), host.rect())
            self.assertEqual(overlay.zoom_factor, 1.0)
            self.assertGreater(overlay._image.width(), chart.width())

            QTest.mouseClick(overlay._plus, Qt.LeftButton)
            self.assertEqual(overlay.zoom_factor, 1.25)
            QTest.mouseClick(overlay._reset, Qt.LeftButton)
            self.assertEqual(overlay.zoom_factor, 1.0)
            self.assertFalse(overlay._minus.isEnabled())
            overlay.close()
            self.app.processEvents()
            self.assertIsNone(controller.overlay)
        finally:
            host.close()

    def test_magnifier_strings_change_for_every_supported_language(self):
        previous = i18n.lang
        chart = QWidget()
        controller = attach_chart_zoom(chart)
        try:
            for language in LANGUAGES:
                with self.subTest(language=language):
                    i18n.set_language(language)
                    self.assertEqual(
                        controller.button.accessibleName(), t("chart_magnifier")
                    )
        finally:
            i18n.set_language(previous)
            chart.close()

    def test_every_chart_family_has_the_shared_magnifier(self):
        widgets = [
            WaveformPanel(show_event_button=False),
            RegionalWaveformPanel(),
            _MultiWave([("T", "#ffffff")]),
            DebugBarChart([0.5] * 16),
            QualityBarChart([0.5] * 16),
            PathologyTab(),
        ]
        try:
            for widget in widgets[:5]:
                with self.subTest(widget=type(widget).__name__):
                    self.assertTrue(hasattr(widget, "_chart_zoom_controller"))
                    self.assertGreaterEqual(
                        widget._chart_zoom_controller.button.minimumHeight(), 46
                    )
            pathology = widgets[-1]
            self.assertTrue(hasattr(pathology._pca_canvas, "_chart_zoom_controller"))
            self.assertTrue(hasattr(pathology._avg_canvas, "_chart_zoom_controller"))
        finally:
            for widget in widgets:
                widget.close()


if __name__ == "__main__":
    unittest.main()
