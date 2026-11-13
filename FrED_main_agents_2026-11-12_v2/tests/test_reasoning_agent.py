import time
import logging

from agents.reasoning_agent import ReasoningAgent
from agents.controller_agent import ControllerAgent

from communication.message_bus import MessageBus
from communication.schemas import (
    Message,
    MessageType,
)

from llm.mock_model import MockLLM


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


bus = MessageBus()

model = MockLLM()
fred = MockFrEDInterface()

reasoning_agent = ReasoningAgent(
    model=model
)

controller_agent = ControllerAgent(
    fred=fred,
    control_enabled=True,  # Enable commands only against the mock hardware.
)

bus.register(reasoning_agent)
bus.register(controller_agent)

reasoning_agent.start()
controller_agent.start()


request = Message(
    sender="user_interface",
    receiver="reasoning_agent",
    message_type=MessageType.REQUEST,
    payload={
        "prompt": "set extrusion to 0.6 rpm"
    },
)

bus.publish(request)

time.sleep(0.5)


print(
    "Final extrusion RPM:",
    fred.extrusion_rpm,
)


assert fred.extrusion_rpm == 0.6


reasoning_agent.stop()
controller_agent.stop()


print("\nStructured reasoning test PASSED")
