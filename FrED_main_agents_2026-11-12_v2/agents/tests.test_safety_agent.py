import time
import logging

from agents.safety_agent import SafetyAgent
from agents.controller_agent import ControllerAgent
from communication.message_bus import MessageBus
from communication.schemas import Message, MessageType


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


bus = MessageBus()

safety_agent = SafetyAgent()
controller_agent = ControllerAgent()

bus.register(safety_agent)
bus.register(controller_agent)

safety_agent.start()
controller_agent.start()


observation = Message(
    sender="perception_agent",
    receiver="safety_agent",
    message_type=MessageType.OBSERVATION,
    payload={
        "distance": 0.20
    },
)

bus.publish(observation)

time.sleep(1)

safety_agent.stop()
controller_agent.stop()