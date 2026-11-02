import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app.application import EventBus, MonitoringService, MonitoringSnapshot, MonitoringView
from app.data_sources import SimulationDataSource
from app.domain import DataQuality
from app.screens.main_screen import MainScreen
from app.widgets.lung_viz import LungVizWidget
from app.widgets.waveform_panel import RegionalWaveformPanel, WaveformPanel


class StaticMonitoring:
    def __init__(self, view: MonitoringView):
        self.view = view
        self.requested_windows = []

    @property
    def snapshot(self):
        return self.view.snapshot

    def get_waveforms(self, window_sec=60.0):
        return self.view.waveforms

    def read_view(self, window_sec=60.0):
        self.requested_windows.append(window_sec)
        return self.view


class LiveMonitoringViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_live_window_freezes_on_pause_and_clears_on_stop(self):
        service = MonitoringService(
            SimulationDataSource(seed=19, playback_speed=100.0),
            EventBus(),
            buffer_seconds=30,
        )
        try:
            service.start()
            service.prime(400)
            live = service.read_view(window_sec=2.0)
            self.assertEqual(live.snapshot.stream_state, "live")
            self.assertEqual(live.waveforms["global"].size, 50)
            self.assertEqual(live.waveforms["global"].size, live.waveforms["rois"][0].size)
            self.assertEqual(len(live.snapshot.reconstruction_map), 64)
            self.assertEqual(len(live.snapshot.reconstruction_map[0]), 64)

            service.suspend()
            frozen = service.read_view(window_sec=2.0)
            frozen_again = service.read_view(window_sec=2.0)
            self.assertEqual(frozen.snapshot.stream_state, "frozen")
            self.assertEqual(frozen.snapshot.quality, DataQuality.STALE)
            self.assertEqual(
                frozen.waveforms["global"].tolist(),
                frozen_again.waveforms["global"].tolist(),
            )
            self.assertEqual(
                frozen.snapshot.reconstruction_map,
                frozen_again.snapshot.reconstruction_map,
            )

            service.stop()
            cleared = service.read_view(window_sec=2.0)
            self.assertEqual(cleared.snapshot.stream_state, "empty")
            self.assertEqual(cleared.snapshot.quality, DataQuality.UNAVAILABLE)
            self.assertEqual(cleared.waveforms["global"].size, 0)
            self.assertIsNone(cleared.snapshot.reconstruction_map)
        finally:
            service.stop()

    def test_main_screen_uses_one_configurable_atomic_view_and_shows_quality(self):
        empty = {"time": [], "global": [], "rois": [[] for _ in range(8)]}
        monitoring = StaticMonitoring(MonitoringView(
            snapshot=MonitoringSnapshot(
                quality=DataQuality.DEGRADED,
                quality_reason="source_quality_degraded",
                stream_state="live",
            ),
            waveforms=empty,
        ))
        screen = MainScreen(monitoring, display_window_sec=12.5)
        try:
            self.assertEqual(monitoring.requested_windows, [12.5])
            self.assertIn("низкое качество", screen._quality_banner.text())
            self.assertIn("источник сообщил низкое качество", screen._quality_banner.toolTip())
            self.assertNotIn("source_quality_degraded", screen._quality_banner.toolTip())
            screen._on_paint()
            self.assertEqual(monitoring.requested_windows, [12.5, 12.5])
        finally:
            screen.close()

    def test_reconstruction_widget_paints_every_map_element_with_native_qt(self):
        reconstruction = tuple(
            tuple(float(row * 64 + column) for column in range(64))
            for row in range(64)
        )
        widget = LungVizWidget()
        widget.resize(260, 260)
        absolute = tuple(
            tuple(0.5 + value / 4096.0 for value in row)
            for row in reconstruction
        )
        widget.update_state(0.5, (12.5,) * 8, reconstruction, absolute)
        fixed_limit = widget.delta_color_limit
        widget.update_state(
            0.6,
            (13.0,) * 8,
            tuple(tuple(value * 10.0 for value in row) for row in reconstruction),
            absolute,
        )
        image = QImage(widget.size(), QImage.Format_ARGB32)
        image.fill(0)
        widget.render(image)
        try:
            self.assertEqual(widget.reconstruction_shape, (64, 64))
            self.assertEqual(widget.display_mode, "absolute")
            self.assertTrue(widget.patient_left_is_screen_left)
            self.assertEqual(widget.delta_color_limit, fixed_limit)
            self.assertEqual(widget.rendered_element_count, 64 * 64)
            self.assertFalse(image.isNull())
            QTest.mouseClick(widget, Qt.LeftButton)
            self.assertEqual(widget.display_mode, "delta")
        finally:
            widget.close()

    def test_regional_waveform_columns_show_left_lung_on_screen_left(self):
        regional = RegionalWaveformPanel()
        dense = WaveformPanel()
        try:
            self.assertIs(
                regional.layout().itemAt(0).widget(),
                regional._col_l.widget,
            )
            self.assertIs(
                regional.layout().itemAt(2).widget(),
                regional._col_r.widget,
            )
            dense_regional = dense.layout().itemAt(3).widget()
            columns = dense_regional.layout()
            self.assertIs(
                columns.itemAt(0).widget().layout().itemAt(0).widget(),
                dense._hdr_l,
            )
            self.assertIs(
                columns.itemAt(2).widget().layout().itemAt(0).widget(),
                dense._hdr_r,
            )
        finally:
            regional.close()
            dense.close()


if __name__ == "__main__":
    unittest.main()
