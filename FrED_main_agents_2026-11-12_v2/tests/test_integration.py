import time
import logging

from agents.reasoning_agent import ReasoningAgent
from agents.safety_agent import SafetyAgent
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


bus = MessageBus()

model = MockLLM()

reasoning_agent = ReasoningAgent(model=model)
safety_agent = SafetyAgent()
controller_agent = ControllerAgent()

bus.register(reasoning_agent)
bus.register(safety_agent)
bus.register(controller_agent)

reasoning_agent.start()
safety_agent.start()
controller_agent.start()


# 1. Simulate an unsafe obstacle observation
observation = Message(
    sender="perception_agent",
    receiver="safety_agent",
    message_type=MessageType.OBSERVATION,
    payload={
        "distance": 0.15
    },
)

bus.publish(observation)

time.sleep(0.5)


# 2. Simulate a user asking the reasoning agent to move forward
request = Message(
    sender="user_interface",
    receiver="reasoning_agent",
    message_type=MessageType.REQUEST,
    payload={
        "prompt": "move forward"
    },
)

bus.publish(request)

time.sleep(1)


reasoning_agent.stop()
safety_agent.stop()
controller_agent.stop()
