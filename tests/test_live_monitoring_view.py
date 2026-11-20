import os
import unittest
from types import SimpleNamespace

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from PySide6.QtCore import QRectF, Qt
from PySide6.QtTest import QTest

from app.application import (
    EngineeringSettings, EngineeringSettingsService, EventBus, MonitoringService,
    MonitoringSnapshot, MonitoringView,
)
from app.data_sources import SimulationDataSource
from app.domain import DataQuality
from app.screens.main_screen import MainScreen
from app.widgets.lung_viz import LungVizWidget
from app.widgets.waveform_panel import (
    RegionalWaveformPanel, WaveformPanel, _relative_markers,
)


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


class MemorySettingsRepository:
    def __init__(self):
        self.values = {}

    def load(self):
        return dict(self.values)

    def save(self, values):
        self.values.update(values)


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
            self.assertEqual(live.waveforms["velocity"].size, 50)
            self.assertTrue(np.all(np.isfinite(live.waveforms["velocity"])))
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

    def test_default_monitoring_buffer_allocates_full_120_second_window(self):
        service = MonitoringService(
            SimulationDataSource(seed=23, playback_speed=100.0),
            EventBus(),
        )
        try:
            self.assertEqual(service._buffer_seconds, 120)
            self.assertEqual(service._aeration._capacity, 3000)
        finally:
            service.stop()

    def test_main_screen_uses_one_configurable_atomic_view_and_ignores_quality(self):
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
            self.assertIn("качество в норме", screen._quality_banner.text())
            self.assertNotIn("источник сообщил низкое качество", screen._quality_banner.toolTip())
            self.assertNotIn("source_quality_degraded", screen._quality_banner.toolTip())
            screen._on_paint()
            self.assertEqual(monitoring.requested_windows, [12.5, 12.5])
        finally:
            screen.close()

    def test_main_screen_applies_saved_graph_display_period_immediately(self):
        empty = {"time": [], "global": [], "rois": [[] for _ in range(8)]}
        monitoring = StaticMonitoring(MonitoringView(
            snapshot=MonitoringSnapshot(),
            waveforms=empty,
        ))
        settings = EngineeringSettingsService(MemorySettingsRepository(), EventBus())
        screen = MainScreen(monitoring, engineering_settings=settings)
        try:
            self.assertEqual(monitoring.requested_windows, [60.0])
            settings.save(EngineeringSettings(graph_display_period_seconds=90))
            screen._on_paint()
            self.assertEqual(monitoring.requested_windows[-1], 90.0)
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
            self.assertGreater(widget.rendered_element_count, 64 * 64 // 2)
            self.assertLess(widget.rendered_element_count, 64 * 64)
            self.assertEqual(
                widget.roi_grid_labels,
                (
                    ("ROI_5", "ROI_1"),
                    ("ROI_6", "ROI_2"),
                    ("ROI_7", "ROI_3"),
                    ("ROI_8", "ROI_4"),
                ),
            )
            self.assertFalse(image.isNull())
            QTest.mouseClick(widget, Qt.LeftButton)
            self.assertEqual(widget.display_mode, "delta")
        finally:
            widget.close()

    def test_reconstruction_roi_grid_tracks_configured_even_roi_count(self):
        widget = LungVizWidget()
        try:
            widget.update_state(0.5, (10.0,) * 10)
            self.assertEqual(
                widget.roi_grid_labels,
                (
                    ("ROI_6", "ROI_1"),
                    ("ROI_7", "ROI_2"),
                    ("ROI_8", "ROI_3"),
                    ("ROI_9", "ROI_4"),
                    ("ROI_10", "ROI_5"),
                ),
            )
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

    def test_expanded_global_metrics_are_doubled_and_stacked_vertically(self):
        panel = WaveformPanel(show_regional=False, expand_global=True)
        try:
            panel.resize(1000, 700)
            panel.show()
            self.app.processEvents()
            row = panel.row_global
            boxes = (row.rr_box, row.pct_box, row.trend_box)
            self.assertEqual([box.height() for box in boxes], [136, 136, 136])
            self.assertEqual([box.width() for box in boxes], [192, 192, 192])
            self.assertLess(row.rr_box.y(), row.pct_box.y())
            self.assertLess(row.pct_box.y(), row.trend_box.y())
            self.assertLessEqual(
                abs(
                    (row.metrics_stack.y() + row.metrics_stack.height() / 2)
                    - row.height() / 2
                ),
                2.0,
            )
        finally:
            panel.close()

    def test_waveform_panel_shows_current_monitoring_moment_on_time_bar(self):
        panel = WaveformPanel(show_regional=False, expand_global=True)
        try:
            times = np.asarray([65.0, 66.0, 67.0])
            signal = np.asarray([1.0, 2.0, 1.5])
            panel.update_all(
                {"time": times, "global": signal, "rois": [signal] * 8},
                15.0,
                [12.5] * 8,
            )
            panel.resize(1000, 700)
            panel.show()
            self.app.processEvents()

            bar = panel.monitoring_moment_bar
            self.assertEqual(bar.start_seconds, 65.0)
            self.assertEqual(bar.current_seconds, 67.0)
            image = bar.grab().toImage()
            self.assertFalse(image.isNull())
        finally:
            panel.close()

    def test_new_event_at_filter_boundary_remains_visible_on_waveform(self):
        marker = SimpleNamespace(
            position_seconds=0.25, event_type="cough", corrects_event_id=None,
        )

        self.assertEqual(
            _relative_markers((marker,), (0.0,)),
            ((1.0, "С1"),),
        )
        self.assertEqual(
            _relative_markers((marker,), (0.28, 0.32)),
            ((0.0, "С1"),),
        )

    def test_lung_visualization_uses_prominent_scaling_outer_contour(self):
        self.assertEqual(LungVizWidget._thorax_contour_width(150), 3.0)
        self.assertEqual(LungVizWidget._thorax_contour_width(600), 5.0)

    def test_lung_visualization_uses_large_landmarks_and_patient_table(self):
        widget = LungVizWidget()
        try:
            widget.resize(500, 420)
            self.assertEqual(widget._orientation_font_size(150, True), 15)
            self.assertEqual(widget._orientation_font_size(360, False), 20)
            self.assertEqual(widget._orientation_font_size(600, False), 28)

            map_rect = QRectF(100, 70, 300, 280)
            landmarks = dict(widget._orientation_rects(map_rect, compact=False))
            self.assertLess(landmarks["L"].right(), map_rect.left())
            self.assertLess(landmarks["V"].bottom(), map_rect.top())
            self.assertGreater(landmarks["R"].left(), map_rect.right())
            self.assertGreater(landmarks["D"].top(), map_rect.bottom())

            table_rect = widget._patient_table_rect(map_rect, compact=False)
            self.assertFalse(table_rect.isEmpty())
            self.assertGreater(table_rect.top(), landmarks["D"].bottom())
            self.assertLess(table_rect.bottom(), widget.height() - 16)
            self.assertGreaterEqual(table_rect.width(), map_rect.width() * 0.75)
            self.assertEqual(table_rect.height(), 7)
        finally:
            widget.close()

    def test_event_labels_are_sequential_and_corrections_do_not_duplicate_lines(self):
        first = SimpleNamespace(position_seconds=1.0, corrects_event_id=None)
        correction = SimpleNamespace(position_seconds=1.0, corrects_event_id="first")
        second = SimpleNamespace(position_seconds=2.0, corrects_event_id=None)

        self.assertEqual(
            _relative_markers((first, correction, second), (0.0, 3.0)),
            ((1 / 3, "С1"), (2 / 3, "С2")),
        )


if __name__ == "__main__":
    unittest.main()
