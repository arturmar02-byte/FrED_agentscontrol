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
        self.stop_all_called = False
        self.extrusion_rpm = 0.0
        self.spooler_duty = 0.0
        self.fan_duty = 0.0

    def stop_all(self):
        self.stop_all_called = True

        self.extrusion_rpm = 0.0
        self.spooler_duty = 0.0
        self.fan_duty = 0.0

    def stop_heater(self):
        pass

    def stop_extruder(self):
        self.extrusion_rpm = 0.0

    def stop_spooler(self):
        self.spooler_duty = 0.0

    def set_extrusion_rpm(self, rpm):
        self.extrusion_rpm = rpm

    def set_spooler_duty(self, duty):
        self.spooler_duty = duty

    def set_fan_duty(self, duty):
        self.fan_duty = duty


fred = MockFrEDInterface()

controller = ControllerAgent(
    fred=fred
)

bus = MessageBus()

bus.register(controller)

controller.start()


command = Message(
    sender="reasoning_agent",
    receiver="controller_agent",
    message_type=MessageType.COMMAND,
    payload={
        "command": "set_extrusion_rpm",
        "rpm": 0.6,
    },
)

bus.publish(command)

time.sleep(0.3)


print(
    "Extrusion RPM:",
    fred.extrusion_rpm,
)


alert = Message(
    sender="safety_agent",
    receiver="controller_agent",
    message_type=MessageType.ALERT,
    payload={
        "event": "critical_condition",
        "action": "stop",
    },
    priority=10,
)

bus.publish(alert)

time.sleep(0.3)


print(
    "STOP ALL called:",
    fred.stop_all_called,
)

print(
    "Extrusion RPM after stop:",
    fred.extrusion_rpm,
)


assert fred.extrusion_rpm == 0.0
assert fred.stop_all_called is True


controller.stop()


print("\nController hardware test PASSED")