import time
import logging

from agents.perception_agent import PerceptionAgent
from agents.safety_agent import SafetyAgent
from agents.controller_agent import ControllerAgent

from communication.message_bus import MessageBus


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


class MockFrEDInterface:

    def __init__(self):

        self.temperature = 120.0
        self.diameter = 0.35
        self.spooler_rpm = 30.0

        self.stop_all_called = False

    # =========================================================
    # SENSOR READS
    # =========================================================

    def get_temperature(self):
        return self.temperature

    def get_diameter(self):
        return self.diameter

    def get_spooler_rpm(self):
        return self.spooler_rpm

    def get_diameter_status(self):

        return {
            "diameter": self.diameter,
            "found": True,
            "age": 0.1,
            "streaming": True,
        }

    # =========================================================
    # HARDWARE COMMANDS
    # =========================================================

    def stop_all(self):

        self.stop_all_called = True

    def stop_heater(self):
        pass

    def stop_extruder(self):
        pass

    def stop_spooler(self):
        pass

    def set_extrusion_rpm(self, rpm):
        pass

    def set_spooler_duty(self, duty):
        pass

    def set_fan_duty(self, duty):
        pass


fred = MockFrEDInterface()

bus = MessageBus()


perception_agent = PerceptionAgent(
    fred=fred
)

safety_agent = SafetyAgent()

controller_agent = ControllerAgent(
    fred=fred
)


bus.register(perception_agent)
bus.register(safety_agent)
bus.register(controller_agent)


perception_agent.start()
safety_agent.start()
controller_agent.start()


# ============================================================
# SAFE STATE
# ============================================================

time.sleep(0.5)

print(
    "STOP during safe state:",
    fred.stop_all_called,
)

assert fred.stop_all_called is False


# ============================================================
# SIMULATE OVER-TEMPERATURE
# ============================================================

print(
    "\nSimulating temperature increase..."
)

fred.temperature = 230.0


time.sleep(0.5)


print(
    "STOP after overheating:",
    fred.stop_all_called,
)

assert fred.stop_all_called is True


perception_agent.stop()
safety_agent.stop()
controller_agent.stop()


print(
    "\nPerception integration test PASSED"
)