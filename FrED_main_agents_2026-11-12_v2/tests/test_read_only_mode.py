import time
import logging

from agents.controller_agent import ControllerAgent

from communication.message_bus import MessageBus
from communication.schemas import (
    Message,
    MessageType,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


class MockFrEDInterface:

    def __init__(self):
        self.fan_duty = 0.0
        self.extrusion_rpm = 0.0
        self.spooler_duty = 0.0

        self.stop_all_called = False

    def set_fan_duty(self, duty):
        self.fan_duty = duty

    def set_extrusion_rpm(self, rpm):
        self.extrusion_rpm = rpm

    def set_spooler_duty(self, duty):
        self.spooler_duty = duty

    def stop_heater(self):
        pass

    def stop_extruder(self):
        self.extrusion_rpm = 0.0

    def stop_spooler(self):
        self.spooler_duty = 0.0

    def stop_all(self):
        self.stop_all_called = True

        self.fan_duty = 0.0
        self.extrusion_rpm = 0.0
        self.spooler_duty = 0.0


fred = MockFrEDInterface()

bus = MessageBus()


# IMPORTANT:
# control_enabled is NOT specified.
# Therefore it must default to False.
controller = ControllerAgent(
    fred=fred
)


bus.register(controller)

controller.start()


# ============================================================
# TEST 1
# NORMAL HARDWARE COMMAND MUST BE BLOCKED
# ============================================================

fan_command = Message(
    sender="reasoning_agent",
    receiver="controller_agent",
    message_type=MessageType.COMMAND,
    payload={
        "command": "set_fan_duty",
        "duty_cycle": 60,
    },
)

bus.publish(fan_command)

time.sleep(0.3)


print(
    "Fan duty in read-only mode:",
    fred.fan_duty,
)

assert fred.fan_duty == 0.0


# ============================================================
# TEST 2
# SAFETY STOP MUST STILL WORK
# ============================================================

safety_alert = Message(
    sender="safety_agent",
    receiver="controller_agent",
    message_type=MessageType.ALERT,
    payload={
        "event": "test_emergency",
        "action": "stop",
    },
)

bus.publish(safety_alert)

time.sleep(0.3)


print(
    "STOP ALL called:",
    fred.stop_all_called,
)

print(
    "Emergency stop active:",
    controller.emergency_stop_active,
)


assert fred.stop_all_called is True
assert controller.emergency_stop_active is True


controller.stop()


print(
    "\nRead-only safety test PASSED"
)