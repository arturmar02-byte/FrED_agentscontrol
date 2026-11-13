import time
import logging

from agents.safety_agent import SafetyAgent
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

safety_agent = SafetyAgent()

controller_agent = ControllerAgent(
    fred=fred
)

bus.register(safety_agent)
bus.register(controller_agent)

safety_agent.start()
controller_agent.start()


# ============================================================
# SAFE TEMPERATURE
# ============================================================

safe_observation = Message(
    sender="perception_agent",
    receiver="safety_agent",
    message_type=MessageType.OBSERVATION,
    payload={
        "temperature": 120.0
    },
)

bus.publish(safe_observation)

time.sleep(0.3)


print(
    "STOP after safe temperature:",
    fred.stop_all_called,
)

assert fred.stop_all_called is False


# ============================================================
# DANGEROUS TEMPERATURE
# ============================================================

dangerous_observation = Message(
    sender="perception_agent",
    receiver="safety_agent",
    message_type=MessageType.OBSERVATION,
    payload={
        "temperature": 230.0
    },
)

bus.publish(dangerous_observation)

time.sleep(0.3)


print(
    "STOP after dangerous temperature:",
    fred.stop_all_called,
)

assert fred.stop_all_called is True


safety_agent.stop()
controller_agent.stop()


print(
    "\nTemperature safety test PASSED"
)