import os
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("EIT_DATA_MODE", "simulation")
os.environ.setdefault("EIT_DATABASE_PATH", ":memory:")
os.environ.setdefault("EIT_RAW_DATA_DIR", "/tmp/eit-test-frames")
os.environ.setdefault("EIT_EXPORT_DIR", "/tmp/eit-test-exports")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QLabel, QLineEdit, QMessageBox, QPushButton,
)
from PySide6.QtTest import QTest

from app.main_window import MainWindow
from app.domain import CalibrationStatus, Patient
from app.application import ALL_INTERFACE_ELEMENTS, EngineeringSettings, MonitoringSnapshot
from app.i18n import LANGUAGES, STRINGS, i18n
from app.screens.eit_settings_screen import EITSettingsScreen
from app.screens.event_marker_dialog import EventMarkerDialog
from app.screens.main_screen import (
    MAIN_LEFT_PANEL_MIN_WIDTH,
    MAIN_LEFT_PANEL_WIDTH,
    MAIN_LUNG_VIZ_EXPANDED_HEIGHT,
    MAIN_LUNG_VIZ_MIN_HEIGHT,
    LeftPanel,
)
from app.widgets.waveform_panel import WaveformPanel
from app.styles import C, FONT_BTN_START, FONT_LABEL, FONT_MEDICAL_VALUE, FONT_VALUE
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
                    "express_monitoring",
                    "patient",
                    "eit_settings",
                    "trends",
                    "analysis",
                    "peep",
                    "reports",
                    "export",
                    "system",
                    "service",
                    "debug",
                },
            )
            nav_order = [key for key, _label in window._nav._item_keys]
            self.assertEqual(
                nav_order.index("express_monitoring"), nav_order.index("main") + 1
            )
            self.assertEqual(
                nav_order.index("peep"), nav_order.index("analysis") + 1
            )
            for button in window._nav._buttons.values():
                self.assertGreaterEqual(button.minimumHeight(), 44)
                self.assertIn("padding: 6px 12px", button.styleSheet())
        finally:
            window.close()

    def test_express_monitoring_is_large_live_view_with_engineering_visibility(self):
        window = MainWindow()
        try:
            express = window._screens["express_monitoring"]
            self.assertGreaterEqual(express.lung_viz.minimumWidth(), 360)
            self.assertIn("font-size:46px", express.metric_rr.value.styleSheet())
            self.assertFalse(express.plethysmogram.row_global.canvas.isHidden())

            current = window._container.engineering_settings.current
            window._container.engineering_settings.save(replace(
                current,
                visible_elements=tuple(
                    element for element in current.visible_elements
                    if element not in {
                        "express_monitoring.lung_map",
                        "express_monitoring.metrics",
                    }
                ),
            ))
            self.app.processEvents()
            self.assertTrue(express._lung_panel.isHidden())
            self.assertTrue(express._metrics_panel.isHidden())
            self.assertFalse(express._plethysmogram_panel.isHidden())
        finally:
            window.close()

    def test_active_navigation_item_has_a_visible_surround(self):
        window = MainWindow()
        try:
            window._switch_screen("trends")
            self.app.processEvents()

            active_frame = window._nav._item_frames["trends"]
            self.assertTrue(active_frame.property("active"))
            self.assertIn(
                "background-color: #0b4f91",
                active_frame.styleSheet(),
            )
            self.assertIn("border-left: none", active_frame.styleSheet())
            self.assertIn(
                "background-color: #0b4f91",
                window._screen_surround.styleSheet(),
            )
            self.assertIn("border: 2px solid #2196f3", window._screen_surround.styleSheet())
            self.assertIn("border-right: none", window._screen_surround.styleSheet())
            left_layout = window.header.parentWidget().layout()
            self.assertGreater(
                left_layout.indexOf(window._screen_surround),
                left_layout.indexOf(window.header),
            )
            self.assertFalse(window._nav._item_frames["main"].property("active"))
        finally:
            window.close()

    def test_main_lung_visualization_fills_window_and_restores(self):
        window = MainWindow()
        try:
            window.show()
            self.app.processEvents()
            main = window._screens["main"]
            visualization = main.left.lung_viz
            source_parent = visualization.parentWidget()
            source_layout = source_parent.layout()
            source_index = source_layout.indexOf(visualization)

            QTest.mouseClick(visualization, Qt.LeftButton)
            self.app.processEvents()

            dialog = main._lung_fullscreen_dialog
            self.assertIsNotNone(dialog)
            self.assertFalse(dialog.isFullScreen())
            self.assertEqual(dialog.geometry(), window.geometry())
            self.assertIs(visualization.parentWidget(), dialog)
            self.assertGreaterEqual(dialog.close_button.width(), 48)
            self.assertEqual(dialog.close_button.text(), "×")

            dialog.close_button.click()
            self.app.processEvents()

            self.assertIsNone(main._lung_fullscreen_dialog)
            self.assertIs(visualization.parentWidget(), source_parent)
            self.assertEqual(source_layout.indexOf(visualization), source_index)
        finally:
            window.close()

    def test_engineering_background_color_applies_without_restart(self):
        window = MainWindow()
        try:
            current = window._container.engineering_settings.current
            window._container.engineering_settings.save(replace(
                current,
                application_background_color="#123456",
            ))
            self.app.processEvents()

            self.assertEqual(window._application_background_color, "#123456")
            self.assertIn("background-color: #123456", window.styleSheet())
            self.assertIn(
                "background-color:#123456",
                window._screens["patient"].styleSheet(),
            )
            self.assertEqual(
                window._container.engineering_settings.current.application_background_color,
                "#123456",
            )
        finally:
            window.close()

    def test_engineering_visibility_settings_apply_to_navigation_and_main_screen(self):
        window = MainWindow()
        try:
            current = window._container.engineering_settings.current
            window._container.engineering_settings.save(EngineeringSettings(
                work_modes=current.work_modes,
                roi_count=current.roi_count,
                peak_detection_method=current.peak_detection_method,
                visible_tabs=tuple(
                    tab for tab in current.visible_tabs if tab != "trends"
                ),
                show_main_trends=False,
                show_main_tvi=False,
            ))
            self.app.processEvents()

            main = window._screens["main"]
            self.assertTrue(window._nav._item_frames["trends"].isHidden())
            self.assertFalse(window._nav._buttons["main"].isHidden())
            self.assertFalse(window._nav._buttons["system"].isHidden())
            self.assertTrue(main.left.box_tvi.isHidden())
            self.assertTrue(main.waves.row_global.trend_box.isHidden())
            self.assertTrue(all(
                row.trend_box.isHidden()
                for row in main.waves.rows_l + main.waves.rows_r
            ))
        finally:
            window.close()

    def test_trend_roi_charts_follow_engineering_roi_count(self):
        window = MainWindow()
        try:
            service = window._container.engineering_settings
            trends = window._screens["trends"]

            service.save(replace(service.current, roi_count=4))
            self.app.processEvents()
            regional_codes = {
                code for _label, code, _unit in trends.tab_regional.metrics
            }
            self.assertEqual(len(trends.tab_regional.metrics), 10)
            self.assertEqual(len(trends.tab_all.metrics), 18)
            self.assertIn("roi_4_tvi_au", regional_codes)
            self.assertIn("roi_4_percent", regional_codes)
            self.assertNotIn("roi_5_tvi_au", regional_codes)

            service.save(replace(service.current, roi_count=20))
            self.app.processEvents()
            regional_codes = {
                code for _label, code, _unit in trends.tab_regional.metrics
            }
            self.assertEqual(len(trends.tab_regional.metrics), 42)
            self.assertEqual(len(trends.tab_all.metrics), 50)
            self.assertIn("roi_20_tvi_au", regional_codes)
            self.assertIn("roi_20_percent", regional_codes)
        finally:
            window.close()

    def test_trend_tab_shows_matching_numeric_table_and_charts(self):
        window = MainWindow()
        try:
            tab = window._screens["trends"].tab_global
            times = np.asarray([0.0, 15.0, 30.0])
            values = {
                code: np.asarray([index + 0.125, np.nan, index + 2.5])
                for index, (_label, code, _unit) in enumerate(tab.metrics)
            }
            tab.refresh({
                "metrics": values,
                "time": times,
                "axis_range": (0.0, 30.0),
            })

            self.assertEqual(tab.layout().stretch(0), tab.layout().stretch(2))
            self.assertEqual(tab.table.rowCount(), len(tab.metrics))
            self.assertEqual(tab.table.columnCount(), 3)
            self.assertEqual(tab.table.horizontalHeaderItem(1).text(), "15с")
            self.assertEqual(tab.table.item(0, 0).text(), "0")
            self.assertEqual(tab.table.item(0, 0).data(Qt.UserRole), 0.125)
            self.assertEqual(tab.table.item(0, 1).text(), "—")
            self.assertEqual(tab.table.item(0, 2).data(Qt.UserRole), 2.5)
            self.assertGreater(
                tab.table.horizontalHeader().font().pixelSize(),
                tab.table.font().pixelSize(),
            )
            self.assertGreater(
                tab.table.verticalHeader().font().pixelSize(),
                tab.table.font().pixelSize(),
            )
            self.assertGreaterEqual(tab.table.verticalHeader().minimumWidth(), 190)
            self.assertGreaterEqual(tab.table.horizontalHeader().minimumHeight(), 48)
            self.assertEqual(tab.table_panel.objectName(), "trend_table_panel")
            for color_key in ("bg_table", "bg_table_alt", "bg_table_header"):
                self.assertIn(C[color_key], tab.table.styleSheet())
            self.assertIn(C["bg_table"], tab.table_panel.styleSheet())
            rgb_sum = lambda color: sum(
                int(color[index:index + 2], 16) for index in (1, 3, 5)
            )
            self.assertGreater(rgb_sum(C["bg_table"]), rgb_sum(C["bg_main"]))
            np.testing.assert_allclose(
                tab.wave._data[0], values[tab.metrics[0][1]], equal_nan=True
            )
        finally:
            window.close()

    def test_trend_table_arrows_pause_and_resume_latest_column_following(self):
        window = MainWindow()
        try:
            trends = window._screens["trends"]
            trends._timer.stop()
            window.resize(1280, 800)
            window._switch_screen("trends")
            window.show()
            self.app.processEvents()

            tab = trends.tab_global
            times = np.arange(0.0, 15.0 * 40, 15.0)
            values = {
                code: np.arange(times.size, dtype=float) + index
                for index, (_label, code, _unit) in enumerate(tab.metrics)
            }
            tab.refresh({
                "metrics": values,
                "time": times,
                "axis_range": (0.0, float(times[-1])),
            })
            QTest.qWait(20)
            self.app.processEvents()

            scrollbar = tab.table.horizontalScrollBar()
            self.assertGreater(scrollbar.maximum(), 0)
            self.assertEqual(scrollbar.value(), scrollbar.maximum())
            self.assertTrue(tab.table.follow_latest)
            self.assertGreaterEqual(tab.table_previous_button.width(), 64)
            self.assertGreaterEqual(tab.table_previous_button.height(), 48)
            self.assertTrue(tab.table_previous_button.isEnabled())
            self.assertFalse(tab.table_next_button.isEnabled())

            QTest.mouseClick(tab.table_previous_button, Qt.LeftButton)
            self.app.processEvents()
            history_position = scrollbar.value()
            self.assertLess(history_position, scrollbar.maximum())
            self.assertFalse(tab.table.follow_latest)
            self.assertEqual(tab.table_follow_label.text(), "Просмотр истории")

            extended_times = np.append(times, times[-1] + 15.0)
            extended_values = {
                code: np.append(series, series[-1] + 1.0)
                for code, series in values.items()
            }
            tab.refresh({
                "metrics": extended_values,
                "time": extended_times,
                "axis_range": (0.0, float(extended_times[-1])),
            })
            QTest.qWait(20)
            self.app.processEvents()
            self.assertEqual(scrollbar.value(), history_position)
            self.assertLess(scrollbar.value(), scrollbar.maximum())

            for _ in range(tab.table.columnCount() + 1):
                if not tab.table_next_button.isEnabled():
                    break
                QTest.mouseClick(tab.table_next_button, Qt.LeftButton)
                self.app.processEvents()
            self.assertEqual(scrollbar.value(), scrollbar.maximum())
            self.assertTrue(tab.table.follow_latest)
            self.assertEqual(tab.table_follow_label.text(), "Последние данные")

            newest_times = np.append(extended_times, extended_times[-1] + 15.0)
            newest_values = {
                code: np.append(series, series[-1] + 1.0)
                for code, series in extended_values.items()
            }
            tab.refresh({
                "metrics": newest_values,
                "time": newest_times,
                "axis_range": (0.0, float(newest_times[-1])),
            })
            QTest.qWait(20)
            self.app.processEvents()
            self.assertEqual(scrollbar.value(), scrollbar.maximum())
        finally:
            window.close()

    def test_engineering_element_visibility_applies_across_screens(self):
        window = MainWindow()
        try:
            current = window._container.engineering_settings.current
            hidden = {
                "main.rl",
                "main.mvi",
                "main.respiratory_rate",
                "main.velocity",
                "main.global_waveform",
                "patient.history",
                "trends.period",
                "analysis.lung_map",
                "peep.map",
                "eit_settings.visualization",
                "reports.preview",
                "export.summary",
                "service.filters",
                "system.information",
                "debug.chart",
            }
            window._container.engineering_settings.save(EngineeringSettings(
                work_modes=current.work_modes,
                roi_count=current.roi_count,
                peak_detection_method=current.peak_detection_method,
                visible_tabs=current.visible_tabs,
                visible_elements=tuple(
                    element for element in ALL_INTERFACE_ELEMENTS if element not in hidden
                ),
            ))
            self.app.processEvents()

            self.assertTrue(window._screens["main"].left.box_lr.isHidden())
            self.assertTrue(window._screens["main"].left.box_mvi.isHidden())
            self.assertTrue(window._screens["main"].left.box_rr.isHidden())
            self.assertTrue(window._screens["main"].waves.row_global.rr_box.isHidden())
            self.assertTrue(window._screens["main"].waves.row_global.isHidden())
            self.assertTrue(window._screens["main"].waves.row_velocity.isHidden())
            self.assertTrue(window._screens["patient"]._box_history.isHidden())
            self.assertTrue(window._screens["trends"]._selector.isHidden())
            self.assertTrue(window._screens["analysis"]._reg_tab.lung_viz.isHidden())
            self.assertTrue(window._screens["peep"]._tab.map_widget.isHidden())
            self.assertTrue(window._screens["eit_settings"]._grp_color.isHidden())
            self.assertTrue(window._screens["reports"]._box_preview.isHidden())
            self.assertTrue(window._screens["export"]._privacy.isHidden())
            self.assertTrue(window._screens["service"]._combo_filter.isHidden())
            self.assertFalse(window._screens["system"]._tabs.isTabVisible(0))
            self.assertTrue(window._screens["debug"]._chart.isHidden())
        finally:
            window.close()

    def test_graph_display_period_applies_to_main_and_analysis_screens(self):
        window = MainWindow()
        try:
            service = window._container.engineering_settings
            service.save(replace(
                service.current,
                graph_display_period_seconds=90,
                trend_point_mode="breath_cycle",
                trend_downsampling_mode="manual_infant",
                trend_chart_mode="lines",
            ))
            self.app.processEvents()

            self.assertEqual(window._screens["main"]._display_window_sec, 90.0)
            self.assertEqual(window._screens["analysis"]._display_window_sec, 90.0)
            self.assertEqual(
                window._screens["trends"]._trend_point_mode, "breath_cycle"
            )
            self.assertEqual(
                window._screens["trends"]._trend_downsampling_mode,
                "manual_infant",
            )
            self.assertEqual(
                window._screens["trends"]._trend_chart_mode, "lines"
            )
            self.assertTrue(all(
                wave._chart_mode == "lines"
                for wave in window._screens["trends"]._trend_waves()
            ))
        finally:
            window.close()

    def test_engineering_aeration_parameters_are_hidden_everywhere(self):
        window = MainWindow()
        try:
            service = window._container.engineering_settings
            hidden_trends = (
                "tvi_au",
                "mvi_au_per_min",
                "roi_1_percent",
            )
            hidden_globally = (
                "total_percent",
                "eeli_au",
                "right_left_ratio",
            )
            engineering = window._screens["system"]
            for code in hidden_trends:
                engineering._trend_visibility_checks[code].setChecked(False)
            for code in hidden_globally:
                engineering._aeration_visibility_checks[code].setChecked(False)
            engineering._engineering_apply.click()
            self.app.processEvents()
            self.assertEqual(
                service.current.hidden_trend_metrics, hidden_trends
            )
            self.assertEqual(
                service.current.hidden_aeration_metrics, hidden_globally
            )

            main = window._screens["main"]
            self.assertTrue(main.left.box_t.isHidden())
            self.assertTrue(main.left.box_eeli.isHidden())
            self.assertFalse(main.left.box_tvi.isHidden())
            self.assertFalse(main.left.box_mvi.isHidden())
            self.assertTrue(main.left.box_lr.isHidden())
            self.assertTrue(main.waves.row_global.pct_box.isHidden())
            self.assertFalse(main.waves.rows_r[0].pct_box.isHidden())
            self.assertFalse(main.left.box_eili.isHidden())

            express = window._screens["express_monitoring"]
            self.assertTrue(express.metric_eeli.isHidden())
            self.assertFalse(express.metric_tvi.isHidden())
            self.assertFalse(express.metric_mvi.isHidden())
            self.assertTrue(express.metric_rl.isHidden())
            self.assertFalse(express.metric_eili.isHidden())

            analysis = window._screens["analysis"]
            self.assertTrue(analysis._global_tab._left.bx_t.isHidden())
            self.assertTrue(analysis._global_tab._left.bx_lr.isHidden())
            self.assertTrue(analysis._reg_tab.bx_t.isHidden())
            self.assertTrue(analysis._reg_tab.bx_lr.isHidden())
            self.assertFalse(
                analysis._reg_tab._waves._col_r.rois[0].pct_box.isHidden()
            )

            trends = window._screens["trends"]
            for tab in trends._trend_tabs():
                codes = {code for _label, code, _unit in tab.metrics}
                self.assertTrue(
                    codes.isdisjoint(hidden_trends + hidden_globally)
                )
            self.assertEqual(trends.tab_global.table.rowCount(), 4)
            self.assertEqual(trends.tab_regional.table.rowCount(), 17)

            all_global_codes = tuple(
                code for _label, code, _unit in trends.tab_global.metrics
            )
            service.save(replace(
                service.current,
                hidden_trend_metrics=hidden_trends + all_global_codes,
            ))
            self.app.processEvents()
            self.assertEqual(trends.tab_global.metrics, ())
            self.assertFalse(trends.tab_global.empty_label.isHidden())

            service.save(replace(
                service.current,
                hidden_trend_metrics=(),
                hidden_aeration_metrics=(),
            ))
            self.app.processEvents()
            self.assertFalse(main.left.box_tvi.isHidden())
            self.assertFalse(express.metric_tvi.isHidden())
            self.assertFalse(analysis._global_tab._left.bx_lr.isHidden())
            self.assertFalse(main.waves.rows_r[0].pct_box.isHidden())
            self.assertIn(
                "tvi_au",
                {code for _label, code, _unit in trends.tab_global.metrics},
            )
        finally:
            window.close()

    def test_velocity_and_global_aeration_charts_are_vertically_aligned(self):
        waves = WaveformPanel(show_velocity=True, roi_count=8)
        try:
            waves.resize(1200, 760)
            waves.show()
            self.app.processEvents()
            global_canvas = waves.row_global.canvas.geometry()
            velocity_canvas = waves.row_velocity.canvas.geometry()

            self.assertEqual(global_canvas.x(), velocity_canvas.x())
            self.assertEqual(global_canvas.width(), velocity_canvas.width())
            self.assertLessEqual(
                waves.row_global.geometry().bottom(),
                waves.row_velocity.geometry().top(),
            )
        finally:
            waves.close()

    def test_existing_eit_defaults_stay_at_one_belt_and_16_electrodes(self):
        screen = EITSettingsScreen()
        try:
            values = {field.text() for field in screen.findChildren(QLineEdit)}
            self.assertIn("1", values)
            self.assertIn("16", values)
        finally:
            screen.close()

    def test_unavailable_metrics_are_rendered_as_dash_without_obstructive_tooltip(self):
        panel = LeftPanel()
        try:
            panel.update_params(MonitoringSnapshot())
            for box in (
                panel.box_t, panel.box_r, panel.box_l, panel.box_lr,
                panel.box_vd, panel.box_tvi, panel.box_eeli, panel.box_eili,
                panel.box_mvi, panel.box_rr,
            ):
                self.assertEqual(box._lbl_val.text(), "—")
                self.assertEqual(box.toolTip(), "")
        finally:
            panel.close()

    def test_main_screen_uses_enlarged_lung_visualization(self):
        panel = LeftPanel()
        try:
            panel.resize(380, 700)
            panel.show()
            self.app.processEvents()
            self.assertGreaterEqual(panel.lung_viz.minimumHeight(), 300)
            self.assertLessEqual(
                panel.lung_viz.geometry().bottom(),
                panel.box_t.parentWidget().geometry().top(),
            )
            self.assertLessEqual(panel.minimumSizeHint().height(), 700)
        finally:
            panel.close()

    def test_main_left_panel_width_and_lung_visualization_are_balanced(self):
        panel = LeftPanel()
        window = None
        try:
            self.assertEqual(MAIN_LEFT_PANEL_WIDTH, 540)
            self.assertLess(MAIN_LEFT_PANEL_WIDTH, 570)
            self.assertEqual(panel.sizeHint().width(), MAIN_LEFT_PANEL_WIDTH)
            self.assertEqual(panel.minimumWidth(), MAIN_LEFT_PANEL_MIN_WIDTH)
            self.assertEqual(panel.maximumWidth(), MAIN_LEFT_PANEL_WIDTH)

            window = MainWindow()
            window.resize(1512, 982)
            window.show()
            self.app.processEvents()
            main = window._screens["main"]
            self.assertEqual(main.left.width(), MAIN_LEFT_PANEL_WIDTH)
            self.assertEqual(
                main.left.lung_viz.height(),
                MAIN_LUNG_VIZ_EXPANDED_HEIGHT,
            )
            self.assertFalse(main.left.geometry().intersects(main.waves.geometry()))

            window.resize(1280, 800)
            self.app.processEvents()
            self.assertGreaterEqual(main.left.width(), MAIN_LEFT_PANEL_MIN_WIDTH)
            self.assertLessEqual(main.left.width(), MAIN_LEFT_PANEL_WIDTH)
            self.assertEqual(main.left.lung_viz.height(), MAIN_LUNG_VIZ_MIN_HEIGHT)
            self.assertFalse(main.left.geometry().intersects(main.waves.geometry()))
        finally:
            panel.close()
            if window is not None:
                window.close()

    def test_main_screen_displays_impedance_minute_ventilation(self):
        panel = LeftPanel()
        try:
            panel.update_params(MonitoringSnapshot(
                rr=15.0,
                tvi=4.0,
                mvi=60.0,
            ))
            self.assertEqual(panel.box_mvi._lbl_val.text(), "60.0")
            labels = [label.text() for label in panel.box_mvi.findChildren(QLabel)]
            self.assertIn("MVi", labels)
            self.assertNotIn("AU", " ".join(labels))
        finally:
            panel.close()

    def test_main_screen_displays_respiratory_rate_with_numeric_parameters(self):
        window = MainWindow()
        try:
            main = window._screens["main"]
            main.left.update_params(MonitoringSnapshot(rr=15.0))

            self.assertEqual(main.left.box_rr._lbl_val.text(), "15")
            self.assertFalse(main.left.box_rr.isHidden())
            self.assertTrue(main.waves.row_global.rr_box.isHidden())
            self.assertTrue(main.waves.row_velocity.rr_box.isHidden())
        finally:
            window.close()

    def test_main_screen_start_button_keeps_explicit_green_style(self):
        panel = LeftPanel()
        try:
            panel.sync_start(False)
            self.assertIn("background-color: #2e7d32", panel.btn_start.styleSheet())
        finally:
            panel.close()

    def test_main_screen_stop_button_keeps_start_typography(self):
        panel = LeftPanel()
        try:
            panel.sync_start(False)
            start_style = panel.btn_start.styleSheet()
            panel.sync_start(True)
            stop_style = panel.btn_start.styleSheet()
            self.assertIn(f"font-size: {FONT_BTN_START}px", start_style)
            self.assertIn(f"font-size: {FONT_BTN_START}px", stop_style)
            self.assertIn("font-weight: bold", start_style)
            self.assertIn("font-weight: bold", stop_style)
        finally:
            panel.close()

    def test_main_timers_are_single_line_left_of_event_marker(self):
        window = MainWindow()
        try:
            main = window._screens["main"]
            counters = main.left.counters
            bottom_layout = main.waves._bottom_layout

            self.assertIs(counters.parentWidget(), main.waves._bottom_bar)
            self.assertLess(
                bottom_layout.indexOf(counters),
                bottom_layout.indexOf(main.waves.btn_event),
            )
            self.assertIn(
                f"font-size:{FONT_LABEL + 2}px",
                counters.cnt_eit._lbl.styleSheet(),
            )
            self.assertFalse(counters.cnt_eit._lbl.wordWrap())
            self.assertFalse(counters.cnt_es._lbl.wordWrap())
            self.assertIn(
                f"font-size:{FONT_VALUE + 8}px",
                counters.cnt_eit._val.styleSheet(),
            )
            self.assertGreaterEqual(
                main.waves._bottom_bar.minimumHeight(),
                counters.sizeHint().height() + 8,
            )
        finally:
            window.close()

    def test_key_medical_values_use_large_readable_typography(self):
        window = MainWindow()
        try:
            expected = f"font-size:{FONT_MEDICAL_VALUE}px"
            main = window._screens["main"]
            analysis = window._screens["analysis"]
            trends = window._screens["trends"]

            self.assertIn(expected, main.left.box_t._lbl_val.styleSheet())
            self.assertIn(expected, analysis._global_tab._left.bx_rr._v.styleSheet())
            self.assertIn(
                f"font-size: {FONT_MEDICAL_VALUE * 2}px",
                analysis._global_tab._waves.row_global.lbl_rr_val.styleSheet(),
            )
            self.assertEqual(trends.stack.count(), 3)
            global_codes = {code for _label, code, _unit in trends.tab_global.metrics}
            regional_codes = {code for _label, code, _unit in trends.tab_regional.metrics}
            self.assertEqual(len(trends.tab_all.metrics), 26)
            self.assertTrue({
                "eeli_au", "eili_au", "tvi_au", "mli_au",
                "mvi_au_per_min", "rr_bpm", "right_left_ratio",
                "ventral_dorsal_ratio",
            }.issubset(global_codes))
            self.assertTrue({
                "right_percent", "left_percent", "roi_1_tvi_au",
                "roi_8_tvi_au", "roi_1_percent", "roi_8_percent",
            }.issubset(regional_codes))
            self.assertTrue(all(
                "AU" not in unit
                for _label, _code, unit in trends.tab_all.metrics
            ))
            trends.tab_all.wave.grab()
            self.assertGreater(trends.tab_all.wave._plot_left_margin, 58)
            self.assertGreater(
                trends.tab_all.wave.minimumHeight(), trends.tab_all.height()
            )
        finally:
            window.close()

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
            self.assertTrue(all(button.isEnabled() for button in window._study_buttons))
            self.assertTrue(all(button.text() == "▶  СТАРТ" for button in window._study_buttons))
        finally:
            window.close()

    def test_main_start_automatically_links_placeholder_patient_and_study(self):
        window = MainWindow()
        try:
            lifecycle = window._container.study_lifecycle
            self.assertIsNone(lifecycle.selected_patient_id)
            self.assertIsNone(lifecycle.current_study)
            self.assertTrue(window._screens["main"].left.btn_start.isEnabled())

            window._screens["main"].left.btn_start.click()
            self.app.processEvents()

            patient = window._container.repositories.patients.get(
                lifecycle.selected_patient_id
            )
            self.assertEqual(patient.external_id, "AUTO-PATIENT")
            self.assertEqual(lifecycle.current_study.patient_id, patient.id)
            self.assertEqual(lifecycle.status.value, "running")
            self.assertTrue(window._container.monitoring_controller.is_running)

            with patch("app.main_window.QMessageBox.exec", return_value=QMessageBox.Yes):
                window._screens["main"].left.btn_start.click()
            self.app.processEvents()
            self.assertTrue(window._screens["main"].left.btn_start.isEnabled())

            window._screens["main"].left.btn_start.click()
            self.app.processEvents()
            self.assertEqual(lifecycle.status.value, "running")
            self.assertEqual(
                len(window._container.repositories.patients.search("AUTO-PATIENT")),
                1,
            )
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

    def test_patient_screen_imports_csv_as_read_only_playback(self):
        path = Path("example/f1/stats.csv")
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
            self.assertEqual(len(window._container.monitoring.source.recording.frames), 91)
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
            self.assertEqual(len(window._marker_buttons), 6)
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
            self.assertTrue(trends.tab_global.wave._markers)
            self.assertEqual(
                trends.tab_global.wave._axis_end
                - trends.tab_global.wave._axis_start,
                300.0,
            )

            journal = window._screens["service"]
            journal.refresh()
            self.assertEqual(journal._events[0]["event"], marker)
            self.assertIn("ui-doctor", journal._events[0]["desc"])

            window._container.monitoring_controller.stop()
            lifecycle.create_study(author="second-doctor")
            journal.refresh()
            self.assertEqual(journal._events, [])

            journal._combo_scope.setCurrentIndex(1)
            self.app.processEvents()
            self.assertEqual(journal._events[0]["event"], marker)
            self.assertIn("Исследование", journal._events[0]["desc"])
            self.assertFalse(journal._events[0]["can_correct"])
        finally:
            window.close()

    def test_event_marker_button_saves_immediately_and_type_button_closes_dialog(self):
        window = MainWindow()
        try:
            lifecycle = window._container.study_lifecycle
            patient = Patient(external_id="P-UI-MARKER-DIALOG")
            window._container.repositories.patients.save(patient)
            lifecycle.select_patient(patient.id)
            lifecycle.create_study(author="ui-doctor")
            lifecycle.prepare()
            window._container.monitoring_controller.start()
            window._sync_study_controls()

            marker_counts_while_open = []

            def submit_dialog():
                dialog = next(
                    widget for widget in QApplication.topLevelWidgets()
                    if isinstance(widget, EventMarkerDialog)
                )
                marker_counts_while_open.append(len(
                    window._container.marker_service.list_for_current_study()
                ))
                self.assertFalse(dialog.findChildren(QLineEdit))
                choices = {
                    button.property("event_type"): button
                    for button in dialog.findChildren(QPushButton)
                }
                self.assertEqual(
                    set(choices),
                    {"cough", "procedure", "position_change", "operator_note"},
                )
                self.assertTrue(all(button.minimumHeight() >= 100 for button in choices.values()))
                choices["cough"].click()

            QTimer.singleShot(0, submit_dialog)
            window._screens["main"].waves.btn_event.click()

            markers = window._container.marker_service.list_for_current_study()
            self.assertEqual(marker_counts_while_open, [1])
            self.assertEqual(len(markers), 2)
            self.assertEqual(markers[0].text, "")
            self.assertEqual(markers[0].author, "ui-doctor")
            self.assertEqual(markers[0].event_type, "operator_note")
            self.assertEqual(markers[1].event_type, "cough")
            self.assertEqual(markers[1].corrects_event_id, markers[0].id)
            self.assertEqual(markers[1].position_seconds, markers[0].position_seconds)
        finally:
            window.close()

    def test_event_journal_filters_use_two_non_overlapping_rows(self):
        window = MainWindow()
        try:
            window.resize(1280, 800)
            window.show()
            window._switch_screen("service")
            self.app.processEvents()
            journal = window._screens["service"]

            self.assertLess(
                journal._combo_filter.geometry().right(),
                journal._edit_search.geometry().left(),
            )
            self.assertLess(
                journal._edit_search.geometry().right(),
                journal._btn_add.geometry().left(),
            )
            self.assertGreater(
                journal._date_from.geometry().top(),
                journal._combo_filter.geometry().bottom(),
            )
            self.assertLess(
                journal._date_from.geometry().right(),
                journal._date_to.geometry().left(),
            )
            self.assertGreaterEqual(
                journal._btn_add.width(), journal._btn_add.sizeHint().width()
            )
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
