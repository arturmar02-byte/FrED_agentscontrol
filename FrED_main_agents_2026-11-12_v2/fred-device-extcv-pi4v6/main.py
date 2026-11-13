"""Normal FrED entry point: hardware, agents, performance display and local camera."""
import argparse
import logging
from pathlib import Path
import signal
import sys
import threading
import time

# The hardware folder is also runnable directly, with agents in the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import RPi.GPIO as GPIO
from PyQt5.QtCore import QTimer
from database import Database
from user_interface import UserInterface
from fan import Fan
from spooler import Spooler
from extruder import Extruder
from agent_runtime import AgentRuntime
from hardware.pi_runtime import PiAgentInterface, service_agent_stop
from hardware.local_startup import acquire_device_lock, launch_camera, stop_camera

# Hardware-control loop poll period. The loop now only reads sensors / runs the
# PID / appends data - the plots are redrawn on the GUI thread by a QTimer
# (UserInterface.Plot.redraw), so drawing no longer blocks sampling. With that
# bottleneck gone, the loop polls at ~500 Hz so it can comfortably service the
# user-selectable sampling rate (UserInterface.get_sample_period) up to 100 Hz.
# Camera/CV runs in a separate process and does not execute in this loop.
LOOP_SLEEP = 0.002

def hardware_control(gui: UserInterface, shutdown, ready) -> None:
    """Thread to handle hardware control"""
    runtime = None
    fan = spooler = extruder = None
    init_time = time.monotonic()
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        fan = Fan(gui)
        spooler = Spooler(gui)
        fan.start(1000, 0)
        spooler.start(1000, 0)
        extruder = Extruder(gui)
        interface = PiAgentInterface(extruder=extruder, spooler=spooler,
                                     fan=fan, diameter=gui.diameter_source,
                                     database=Database, gui=gui)
        runtime = AgentRuntime(interface, enable_control=False, enable_reasoning=True,
                               metrics_dir=getattr(gui, "metrics_dir", None),
                               context=lambda: {"run_id": gui.experiment.run_id,
                                                "experiment_phase": gui.experiment.phase})
        interface.metrics = runtime.metrics
        gui.agent_runtime = runtime
        runtime.start()
        ready.set()

        init_time = time.monotonic()
        while not shutdown.is_set():
            current_time = time.monotonic() - init_time
            Database.time_readings.append(current_time)

            if service_agent_stop(interface, current_time):
                extruder.monitor_temperature(current_time)
                shutdown.wait(0.02)
                continue

            # Keep real temperature observations available even while idle.
            if not gui.experiment.is_active() and not (
                    gui.device_started or gui.heater_open_loop_enabled):
                extruder.monitor_temperature(current_time)

            # --- Manual STOP requests from the interface (one-shot) --------- #
            # Each Stop button just sets a flag; we service it here so the
            # actuator output is actively driven to zero, not left at its last
            # value. The control flags are already cleared by the UI handler.
            stop_pressed = (gui.stepper_stop_requested or
                            gui.heater_stop_requested or
                            gui.dc_motor_stop_requested)
            if gui.stepper_stop_requested:
                extruder.stop_stepper()
                gui.stepper_stop_requested = False
            if gui.heater_stop_requested:
                extruder.stop_heater()
                gui.heater_stop_requested = False
            if gui.dc_motor_stop_requested:
                spooler.stop_motor()
                gui.dc_motor_stop_requested = False

            if gui.start_motor_calibration:
                spooler.calibrate()
                gui.start_motor_calibration = False

            # --- Remote experiment: an automated run sent from the laptop.
            #     While it is active it owns the hardware (manual controls are
            #     ignored), EXCEPT the STOP buttons, which abort it for safety. ---
            if gui.experiment.is_active():
                if stop_pressed:
                    gui.experiment.abort()
                # update() services a pending abort first (from a STOP button
                # here or the laptop's Abort): it stops heater, stepper,
                # spooler AND fan and clears the manual control flags.
                gui.experiment.update(current_time, extruder, spooler, fan)
                time.sleep(LOOP_SLEEP)
                continue

            # --- Monitor mode: read & graph temperature and spooler RPM with
            #     NO control output applied. Takes priority over the control
            #     loops below so nothing drives the system while observing. ---
            if gui.monitor_mode_enabled:
                extruder.monitor_temperature(current_time)
                spooler.monitor_rpm(current_time)
                if gui.diameter_loop_enabled and (not gui.local or
                        current_time - gui.diameter_source.previous_time >= gui.get_sample_period()):
                    gui.diameter_source.update(current_time)
                fan.control_loop()
                time.sleep(LOOP_SLEEP)
                continue

            # DC Motor Control Logic
            if gui.dc_motor_open_loop_enabled and not gui.dc_motor_close_loop_enabled:
                spooler.dc_motor_open_loop_control(current_time)

            elif gui.dc_motor_close_loop_enabled and not gui.dc_motor_open_loop_enabled:
                spooler.dc_motor_close_loop_control(current_time)

            # Heater Control Logic
            if gui.heater_open_loop_enabled and not gui.device_started:
                extruder.temperature_open_loop_control(current_time)
                extruder.stepper_control_loop()

            # Local or external camera feedback, sampled independently of polling.
            if gui.diameter_loop_enabled and (not gui.local or
                    current_time - gui.diameter_source.previous_time >= gui.get_sample_period()):
                gui.diameter_source.update(current_time)

            if gui.device_started:
                extruder.temperature_control_loop(current_time)
                extruder.stepper_control_loop()

            fan.control_loop()
            time.sleep(LOOP_SLEEP)
    except Exception:
        gui.hardware_failed = True
        logging.exception("Hardware control failed; shutting down FrED")
        shutdown.set()
    finally:
        # Drive outputs to zero before stopping workers or releasing GPIO.
        if extruder is not None:
            try:
                if gui.experiment.is_active():
                    gui.experiment.abort()
                    gui.experiment.update(time.monotonic() - init_time, extruder, spooler, fan)
            except Exception:
                logging.exception("Could not finalize the active experiment")
        actions = []
        if extruder is not None:
            actions.extend((extruder.stop_heater, extruder.stop_stepper))
        if spooler is not None:
            actions.extend((spooler.stop_motor, spooler.stop))
        if fan is not None:
            actions.extend((lambda: fan.update_duty_cycle(0), fan.stop))
        for action in actions:
            try:
                action()
            except Exception:
                logging.exception("Actuator cleanup failed")
        try:
            if runtime is not None:
                runtime.stop()
        finally:
            GPIO.cleanup()

def parse_options(argv=None):
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--local", dest="local", action="store_true", help="Local USB camera (default).")
    source.add_argument("--external-camera", dest="local", action="store_false", help="Receive diameter from another computer.")
    parser.set_defaults(local=True)
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--no-camera-ui", action="store_true", help="Do not open the local camera application automatically.")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--data-dir", type=Path, default=root / "Data")
    parser.add_argument("--metrics-dir", type=Path, help="Defaults to DATA_DIR/agent_metrics.")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between 0 and 65535.")
    if args.camera < 0 or not 1 <= args.fps <= 120 or any(
            value is not None and value <= 0 for value in (args.width, args.height)):
        parser.error("Use a nonnegative camera index, positive dimensions and FPS in [1, 120].")
    args.data_dir = args.data_dir.resolve()
    args.metrics_dir = args.metrics_dir.resolve() if args.metrics_dir else args.data_dir / "agent_metrics"
    if args.calibration:
        args.calibration = args.calibration.resolve()
        if not args.calibration.is_file():
            parser.error("The selected camera calibration does not exist.")
    return args


def main(argv=None):
    args = parse_options(argv)
    logging.basicConfig(level=logging.WARNING)
    print("Starting FrED Device...")
    try:
        hardware_lock = acquire_device_lock()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    # Database calibration paths are relative to the device program's folder.
    import os
    os.chdir(Path(__file__).resolve().parent)
    ui = UserInterface(local=args.local, port=args.port)
    ui.metrics_dir = args.metrics_dir
    ui.hardware_failed = False
    if args.local:
        ui.fan_enabled = False
        ui.diameter_loop_enabled = True
    shutdown = threading.Event()
    ready = threading.Event()
    camera = None
    ui.app.aboutToQuit.connect(shutdown.set)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: shutdown.set())

    hardware_thread = threading.Thread(target=hardware_control, args=(ui, shutdown, ready),
                                       name="fred-hardware")
    hardware_thread.start()

    def poll_lifecycle():
        nonlocal camera
        if shutdown.is_set():
            ui.app.quit()
            return
        if ready.is_set() and ui.diameter_source.listening and args.local and not args.no_camera_ui:
            if camera is None:
                try:
                    camera = launch_camera(Path(__file__).resolve().parents[1], args, ui.diameter_source.port)
                except OSError:
                    logging.exception("Could not start the local camera; stopping FrED")
                    ui.hardware_failed = True
                    shutdown.set()
            elif camera.poll() is not None:
                ui.hardware_failed = ui.hardware_failed or camera.returncode != 0
                shutdown.set()

    lifecycle_timer = QTimer()
    lifecycle_timer.timeout.connect(poll_lifecycle)
    lifecycle_timer.start(100)

    # Start GUI (blocking)
    try:
        ui.start_gui()
    finally:
        shutdown.set()
        ui.diameter_source.close()
        hardware_thread.join()
        stop_camera(camera)
        hardware_lock.close()
    print("FrED Device Closed.")
    return 1 if ui.hardware_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

