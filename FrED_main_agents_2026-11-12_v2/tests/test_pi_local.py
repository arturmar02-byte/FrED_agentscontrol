"""Hardware-free checks for local Pi lifecycle, transport and agent ownership."""
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

from agent_runtime import AgentRuntime
from hardware.pi_runtime import PiAgentInterface, service_agent_stop
from tools.prepare_offline import build_pi_bundle
from hardware.local_startup import launch_camera, stop_camera
from tools.verify_bundle import verify

ROOT = Path(__file__).resolve().parents[1]


def load_device_module(filename, modules):
    spec = importlib.util.spec_from_file_location("pi_test_" + Path(filename).stem,
                                                 ROOT / "fred-device-extcv-pi4v6" / filename)
    module = importlib.util.module_from_spec(spec)
    with patch.dict("sys.modules", modules):
        spec.loader.exec_module(module)
    return module


class AgentOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.gui = types.SimpleNamespace(
            agent_stop_latched=False, device_started=True, heater_open_loop_enabled=True,
            dc_motor_open_loop_enabled=True, dc_motor_close_loop_enabled=False,
            fan_enabled=True, experiment=Mock())
        self.gui.experiment.is_active.return_value = False
        self.extruder, self.spooler, self.fan = Mock(), Mock(), Mock()
        self.diameter = Mock()
        self.diameter.measurement_snapshot.return_value = {
            "diameter": 0.35, "valid": True, "found": True, "age": 0.01, "streaming": True}
        self.interface = PiAgentInterface(
            extruder=self.extruder, spooler=self.spooler, fan=self.fan,
            diameter=self.diameter, database=types.SimpleNamespace(
                temperature_readings=[230], spooler_rpm=[10]), gui=self.gui)

    def test_real_agents_request_stop_without_gpio_from_agent_threads(self):
        runtime = AgentRuntime(self.interface, enable_control=False, enable_reasoning=True)
        runtime.start()
        try:
            self.assertTrue(self.interface.stop_requested.wait(2))
            self.extruder.stop_heater.assert_not_called()
            self.fan.update_duty_cycle.assert_not_called()
            self.assertTrue(service_agent_stop(self.interface, 1))
            self.extruder.stop_heater.assert_called_once()
            self.spooler.stop_motor.assert_called_once()
            self.fan.update_duty_cycle.assert_called_once_with(0)
            self.assertTrue(self.gui.agent_stop_latched)
            self.assertFalse(self.gui.device_started)
            self.assertFalse(self.gui.fan_enabled)
            # Latch persists; cooling or a delayed command cannot resume GPIO.
            self.assertTrue(service_agent_stop(self.interface, 2))
            self.extruder.stop_heater.assert_called_once()
        finally:
            runtime.stop()

    def test_stop_aborts_an_experiment_before_manual_outputs(self):
        self.gui.experiment.is_active.return_value = True
        self.interface.stop_all()
        self.assertTrue(service_agent_stop(self.interface, 3))
        self.gui.experiment.abort.assert_called()
        self.gui.experiment.update.assert_called_once_with(3, self.extruder, self.spooler, self.fan)

    def test_stale_or_uncalibrated_diameter_is_not_an_agent_observation(self):
        self.assertEqual(self.interface.get_diameter(), 0.35)
        self.diameter.measurement_snapshot.return_value["valid"] = False
        self.assertIsNone(self.interface.get_diameter())


class LocalTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_device_module("external_diameter.py", {
            "database": types.SimpleNamespace(Database=Mock())})

    def test_loopback_ephemeral_port_measurement_and_latched_rejection(self):
        gui = types.SimpleNamespace(agent_stop_latched=True, experiment=Mock())
        source = self.module.ExternalDiameter(None, gui, host="127.0.0.1", port=0)
        self.addCleanup(source.close)
        deadline = time.monotonic() + 2
        while not source.listening and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(source.listening)
        self.assertGreater(source.port, 0)
        self.assertEqual(source._server_sock.getsockname()[0], "127.0.0.1")
        with socket.create_connection(("127.0.0.1", source.port), timeout=2) as client:
            client.sendall(b'{"d": 0.35, "u": "mm", "found": true}\n')
            deadline = time.monotonic() + 2
            while not source.measurement_snapshot()["valid"] and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(source.measurement_snapshot()["valid"])
            client.sendall(b'{"type": "experiment", "params": {}}\n')
            reply = json.loads(client.makefile("rb").readline())
            self.assertEqual(reply["event"], "experiment_rejected")
            gui.experiment.start.assert_not_called()


class LifecycleTests(unittest.TestCase):
    def load_hardware(self):
        gpio = Mock()
        extruder, spooler, fan = Mock(), Mock(), Mock()
        module = load_device_module("main.py", {
            "RPi": types.SimpleNamespace(GPIO=gpio), "RPi.GPIO": gpio,
            "PyQt5.QtCore": types.SimpleNamespace(QTimer=Mock()),
            "database": types.SimpleNamespace(Database=types.SimpleNamespace(time_readings=[])),
            "user_interface": types.SimpleNamespace(UserInterface=Mock()),
            "fan": types.SimpleNamespace(Fan=Mock(return_value=fan)),
            "spooler": types.SimpleNamespace(Spooler=Mock(return_value=spooler)),
            "extruder": types.SimpleNamespace(Extruder=Mock(return_value=extruder)),
        })
        return module, gpio, extruder, spooler, fan

    def test_device_loop_stops_and_releases_gpio_when_window_closes(self):
        module, gpio, extruder, spooler, fan = self.load_hardware()
        shutdown, ready = threading.Event(), threading.Event()
        gui = types.SimpleNamespace(local=True, hardware_failed=False, agent_stop_latched=False,
                                    experiment=Mock(), diameter_source=Mock())
        gui.experiment.is_active.return_value = False

        def start_agents(interface, **kwargs):
            interface.stop_all()
            return Mock()

        extruder.monitor_temperature.side_effect = lambda *_: shutdown.set()
        with patch.object(module, "AgentRuntime", side_effect=start_agents):
            module.hardware_control(gui, shutdown, ready)
        self.assertTrue(ready.is_set())
        self.assertTrue(gui.agent_stop_latched)
        fan.start.assert_called_once_with(1000, 0)
        extruder.temperature_control_loop.assert_not_called()
        fan.control_loop.assert_not_called()
        extruder.stop_heater.assert_called()
        spooler.stop.assert_called_once()
        fan.stop.assert_called_once()
        gpio.cleanup.assert_called_once()

    def test_partial_hardware_startup_fails_closed(self):
        module, gpio, extruder, spooler, fan = self.load_hardware()
        module.Extruder.side_effect = RuntimeError("SPI unavailable")
        shutdown, ready = threading.Event(), threading.Event()
        gui = types.SimpleNamespace(hardware_failed=False)
        with self.assertLogs(level="ERROR"):
            module.hardware_control(gui, shutdown, ready)
        self.assertTrue(shutdown.is_set())
        self.assertFalse(ready.is_set())
        self.assertTrue(gui.hardware_failed)
        fan.stop.assert_called_once()
        spooler.stop.assert_called_once()
        gpio.cleanup.assert_called_once()

    def test_camera_child_uses_ready_port_and_supplied_options(self):
        options = types.SimpleNamespace(camera=1, fps=15, data_dir=ROOT / "Data",
                                        width=None, height=None, calibration=None)
        with patch("hardware.local_startup.subprocess.Popen") as launch:
            process = launch_camera(ROOT, options, 54321)
        command = launch.call_args.args[0]
        self.assertIn("--local", command)
        self.assertEqual(command[command.index("--port") + 1], "54321")
        self.assertEqual(command[command.index("--camera") + 1], "1")
        process.poll.return_value = None
        stop_camera(process)
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)

    def test_normal_main_defaults_to_local_camera_and_keeps_external_option(self):
        module, *_ = self.load_hardware()
        options = module.parse_options([])
        self.assertTrue(options.local)
        self.assertFalse(options.no_camera_ui)
        self.assertEqual(options.metrics_dir, ROOT / "Data/agent_metrics")
        self.assertFalse(module.parse_options(["--external-camera"]).local)

    def test_compatibility_alias_replaces_itself_with_regular_main(self):
        from tools.run_pi_local import main as alias_main
        with patch("tools.run_pi_local.os.execv") as execute:
            alias_main(["--camera", "2"])
        arguments = execute.call_args.args[1]
        self.assertEqual(Path(arguments[1]), ROOT / "fred-device-extcv-pi4v6/main.py")
        self.assertEqual(arguments[2:], ["--camera", "2"])

    def test_main_waits_for_hardware_then_owns_camera_and_shutdown(self):
        module, *_ = self.load_hardware()
        ui = Mock()
        ui.hardware_failed = False
        ui.diameter_source.listening = True
        ui.diameter_source.port = 54321
        module.UserInterface.return_value = ui
        order = []
        camera = Mock(returncode=0)
        camera.poll.return_value = 0

        def initialize(gui, shutdown, ready):
            ready.set()

        def make_thread(target, args, **kwargs):
            thread = Mock()
            thread.start.side_effect = lambda: target(*args)
            thread.join.side_effect = lambda: order.append("hardware_stopped")
            return thread

        def gui_loop():
            callback = module.QTimer.return_value.timeout.connect.call_args.args[0]
            callback()  # Readiness has been set; starts the camera.
            callback()  # Camera closed; requests shutdown.
            callback()  # GUI exits on that request.

        ui.start_gui.side_effect = gui_loop
        with patch.object(module, "hardware_control", side_effect=initialize), patch.object(
                module.threading, "Thread", side_effect=make_thread), patch.object(
                module, "acquire_device_lock") as acquire, patch.object(
                module, "launch_camera", return_value=camera) as launch, patch.object(
                module, "stop_camera", side_effect=lambda _: order.append("camera_stopped")), patch.object(
                module.signal, "signal"), patch("os.chdir"):
            self.assertEqual(module.main([]), 0)
        self.assertEqual(launch.call_args.args[2], 54321)
        self.assertEqual(order, ["hardware_stopped", "camera_stopped"])
        acquire.return_value.close.assert_called_once()
        ui.app.quit.assert_called_once()

    def test_main_does_not_open_camera_after_hardware_initialization_failure(self):
        module, *_ = self.load_hardware()
        ui = Mock()
        module.UserInterface.return_value = ui

        def fail(gui, shutdown, ready):
            gui.hardware_failed = True
            shutdown.set()

        def make_thread(target, args, **kwargs):
            thread = Mock()
            thread.start.side_effect = lambda: target(*args)
            return thread

        ui.start_gui.side_effect = lambda: module.QTimer.return_value.timeout.connect.call_args.args[0]()
        with patch.object(module, "hardware_control", side_effect=fail), patch.object(
                module.threading, "Thread", side_effect=make_thread), patch.object(
                module, "acquire_device_lock"), patch.object(module, "launch_camera") as launch, patch.object(
                module, "stop_camera"), patch.object(module.signal, "signal"), patch("os.chdir"):
            self.assertEqual(module.main([]), 1)
        launch.assert_not_called()


class BundleTests(unittest.TestCase):
    def test_pi_bundle_contains_launcher_and_only_example_calibrations(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "FrED_pi_local"
            archive = build_pi_bundle(ROOT, output)
            self.assertTrue(archive.is_file())
            self.assertTrue(verify(output)["ok"])
            self.assertTrue((output / "start_pi_local.sh").is_file())
            self.assertTrue((output / "hardware/pi_runtime.py").is_file())
            self.assertFalse((output / "fred-device-extcv-pi4v6/calibration.yaml").exists())
            self.assertFalse((output / "FrEDFiberMeasurewithStreamingv6/calibration.json").exists())
            self.assertFalse((output / "wheelhouse-laptop").exists())
            self.assertNotIn(b"\r\n", (output / "start_pi_local.sh").read_bytes())
            with self.assertRaises(FileExistsError):
                build_pi_bundle(ROOT, output)


class CameraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "pi_test_camera", ROOT / "FrEDFiberMeasurewithStreamingv6/fiber_measure.py")
        cls.module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(cls.module)
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"Camera dependencies unavailable: {exc}")

    def test_linux_capture_uses_v4l2_and_releases_failed_handle(self):
        module = self.module
        failed, opened = Mock(), Mock()
        failed.isOpened.return_value = False
        opened.isOpened.return_value = True
        app = module.FiberApp.__new__(module.FiberApp)
        app.cam_index_var = Mock()
        app.cam_index_var.get.return_value = 1
        app.status_var = Mock()
        app.capture_width = app.capture_height = None
        app.capture_fps, app.local = 15, True
        with patch.object(module.sys, "platform", "linux"), patch.object(
                module.cv2, "VideoCapture", side_effect=(failed, opened)) as capture:
            app.open_camera()
        self.assertEqual(capture.call_args_list[0].args, (1, module.cv2.CAP_V4L2))
        self.assertEqual(capture.call_args_list[1].args, (1,))
        failed.release.assert_called_once()
        opened.set.assert_any_call(module.cv2.CAP_PROP_FPS, 15)
        self.assertFalse(any(call.args[0] in (module.cv2.CAP_PROP_FRAME_WIDTH,
                                            module.cv2.CAP_PROP_FRAME_HEIGHT)
                             for call in opened.set.call_args_list))

    def test_camera_local_cli_routes_to_loopback_without_creating_a_gui(self):
        module = self.module
        with patch.object(module.tk, "Tk") as root, patch.object(module, "FiberApp") as app, patch.object(
                module.cv2, "setNumThreads") as threads:
            module.main(["--local", "--port", "54321", "--camera", "2", "--fps", "15"])
        self.assertEqual(app.call_args.kwargs["host"], "127.0.0.1")
        self.assertEqual(app.call_args.kwargs["port"], 54321)
        self.assertEqual(app.call_args.kwargs["camera"], 2)
        self.assertTrue(app.call_args.kwargs["local"])
        threads.assert_called_once_with(1)
        root.return_value.mainloop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
