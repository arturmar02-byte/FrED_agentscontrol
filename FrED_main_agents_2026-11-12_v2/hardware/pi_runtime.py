"""Agent access to the Pi: observations and a stop request, never concurrent GPIO."""
import threading
import time

from hardware.fred_interface import FrEDInterface


class PiAgentInterface(FrEDInterface):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stop_requested = threading.Event()
        self.stop_requested_ns = None
        self.stop_message = None
        self.metrics = None

    def get_diameter(self):
        snapshot = self.diameter.measurement_snapshot()
        return snapshot["diameter"] if snapshot["valid"] else None

    def get_diameter_status(self):
        return self.diameter.measurement_snapshot()

    def stop_all(self):
        # Called by an agent thread. The hardware loop owns all GPIO writes.
        if not self.stop_requested.is_set():
            self.stop_requested_ns = time.perf_counter_ns()
            self.stop_requested.set()

    def request_stop(self, message):
        self.stop_message = message
        self.stop_all()


def service_agent_stop(interface, current_time):
    """Enforce a latched stop in the hardware thread, including experiments."""
    if not interface.stop_requested.is_set():
        return False
    gui = interface.gui
    if gui.experiment.is_active():
        gui.experiment.abort()
        gui.experiment.update(current_time, interface.extruder, interface.spooler, interface.fan)
    if not gui.agent_stop_latched:
        FrEDInterface.stop_all(interface)
        gui.agent_stop_latched = True
        if interface.metrics is not None:
            finished_ns = time.perf_counter_ns()
            durations = {"handoff_ms": (finished_ns - interface.stop_requested_ns) / 1e6}
            if interface.stop_message is not None:
                durations["observation_to_stop_ms"] = (finished_ns - interface.stop_message.trace_started_ns) / 1e6
            interface.metrics.record("software_stop_completed", "hardware", durations=durations,
                                     correlation_id=interface.stop_message.message_id if interface.stop_message else None)
    return True
