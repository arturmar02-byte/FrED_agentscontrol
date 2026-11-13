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
        self.extrusion_rpm = 0.0
        self.spooler_duty = 0.0
        self.fan_duty = 0.0

    def set_extrusion_rpm(self, rpm):
        self.extrusion_rpm = rpm

    def set_spooler_duty(self, duty):
        self.spooler_duty = duty

    def set_fan_duty(self, duty):
        self.fan_duty = duty

    def stop_heater(self):
        pass

    def stop_extruder(self):
        self.extrusion_rpm = 0.0

    def stop_spooler(self):
        self.spooler_duty = 0.0

    def stop_all(self):
        self.extrusion_rpm = 0.0
        self.spooler_duty = 0.0
        self.fan_duty = 0.0


fred = MockFrEDInterface()

controller = ControllerAgent(
    fred=fred,
    control_enabled=True,  # Enable commands only against the mock hardware.
)

bus = MessageBus()

bus.register(controller)

controller.start()


# ============================================================
# VALID COMMAND
# ============================================================

valid_command = Message(
    sender="reasoning_agent",
    receiver="controller_agent",
    message_type=MessageType.COMMAND,
    payload={
        "command": "set_extrusion_rpm",
        "rpm": 0.6,
    },
)

bus.publish(valid_command)

time.sleep(0.3)

print(
    "RPM after valid command:",
    fred.extrusion_rpm,
)

assert fred.extrusion_rpm == 0.6


# ============================================================
# INVALID EXTRUSION COMMAND
# ============================================================

invalid_rpm = Message(
    sender="reasoning_agent",
    receiver="controller_agent",
    message_type=MessageType.COMMAND,
    payload={
        "command": "set_extrusion_rpm",
        "rpm": 500,
    },
)

bus.publish(invalid_rpm)

time.sleep(0.3)

print(
    "RPM after invalid command:",
    fred.extrusion_rpm,
)

# Must remain at the previous valid value.
assert fred.extrusion_rpm == 0.6


# ============================================================
# INVALID FAN COMMAND
# ============================================================

invalid_fan = Message(
    sender="reasoning_agent",
    receiver="controller_agent",
    message_type=MessageType.COMMAND,
    payload={
        "command": "set_fan_duty",
        "duty_cycle": 900,
    },
)

bus.publish(invalid_fan)

time.sleep(0.3)

print(
    "Fan after invalid command:",
    fred.fan_duty,
)

assert fred.fan_duty == 0.0


# ============================================================
# VALID FAN COMMAND
# ============================================================

valid_fan = Message(
    sender="reasoning_agent",
    receiver="controller_agent",
    message_type=MessageType.COMMAND,
    payload={
        "command": "set_fan_duty",
        "duty_cycle": 60,
    },
)

bus.publish(valid_fan)

time.sleep(0.3)

print(
    "Fan after valid command:",
    fred.fan_duty,
)

assert fred.fan_duty == 60


controller.stop()

print(
    "\nCommand safety limits test PASSED"
)
