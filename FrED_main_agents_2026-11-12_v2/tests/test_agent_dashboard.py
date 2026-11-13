"""Qt lifecycle checks; skipped when the desktop dependencies are unavailable."""
import importlib.util
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QFontDatabase, QFont
    import matplotlib
except ImportError:
    QApplication = None

from agent_runtime import AgentRuntime
from tests.test_agent_metrics import hardware

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(QApplication is None, "Qt/matplotlib desktop dependencies are not installed")
class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        font = Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"
        QFontDatabase.addApplicationFont(str(font))
        cls.app.setFont(QFont("DejaVu Sans", 10))
        folder = ROOT / "fred-device-extcv-pi4v6"
        with patch.object(sys, "path", [str(folder), *sys.path]):
            spec = importlib.util.spec_from_file_location("dashboard_test_ui", folder / "user_interface.py")
            cls.ui_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.ui_module)

    def test_independent_window_hides_and_reopens_without_stopping_agents(self):
        ui = self.ui_module.UserInterface(local=True, port=0)
        runtime = AgentRuntime(hardware(), enable_reasoning=True)
        ui.agent_runtime = runtime
        runtime.start()
        try:
            ui.window.show()
            display = ui.performance_window
            display.show()
            self.app.processEvents()
            display.prompt.setText("set fan to 30 percent")
            display.submit.click()
            deadline = time.monotonic() + 3
            while runtime.metrics.last_llm_call is None and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.005)
            display.refresh()
            self.assertEqual(display.table.rowCount(), 4)
            self.assertIn("SIMULADOR", display.model.text())
            self.assertIn("set_fan_duty", display.result.toPlainText())
            self.assertEqual(runtime.controller_agent.inbox.qsize(), 0)
            display.close()
            self.app.processEvents()
            self.assertFalse(display.isVisible())
            self.assertTrue(ui.window.isVisible())
            self.assertTrue(runtime.perception_agent._running.is_set())
            display.show()
            self.assertTrue(display.isVisible())
        finally:
            runtime.stop()
            ui.diameter_source.close()
            ui.performance_window.close()
            ui.window.hide()
            ui.window.deleteLater()
            self.app.processEvents()

    def test_closing_main_exits_even_while_performance_window_is_visible(self):
        ui = self.ui_module.UserInterface(local=True, port=0)
        ui.window.show()
        ui.performance_window.show()
        observed = []

        def on_quit():
            observed.append(True)

        self.app.aboutToQuit.connect(on_quit)
        watchdog = QTimer()
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(self.app.quit)
        watchdog.start(2000)
        QTimer.singleShot(0, ui.window.close)
        self.app.exec_()
        self.assertTrue(observed)
        self.assertGreater(watchdog.remainingTime(), 0)
        watchdog.stop()
        self.app.aboutToQuit.disconnect(on_quit)
        ui.diameter_source.close()
        ui.performance_window.close()
        ui.window.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
