import time
import logging

from agents.controller_agent import ControllerAgent
from communication.message_bus import MessageBus
from communication.schemas import Message, MessageType


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


bus = MessageBus()
controller = ControllerAgent()

bus.register(controller)


normal_command = Message(
    sender="reasoning_agent",
    receiver="controller_agent",
    message_type=MessageType.COMMAND,
    payload={
        "command": "move_forward"
    },
    priority=1,
)


critical_alert = Message(
    sender="safety_agent",
    receiver="controller_agent",
    message_type=MessageType.ALERT,
    payload={
        "event": "unsafe_distance",
        "distance": 0.15,
        "action": "stop",
    },
    priority=10,
)


clear_alert = Message(
    sender="safety_agent",
    receiver="controller_agent",
    message_type=MessageType.ALERT,
    payload={
        "event": "safe_distance_restored",
        "action": "clear",
    },
    priority=10,
)


bus.publish(normal_command)
bus.publish(critical_alert)

controller.start()

time.sleep(0.5)


# Command should be rejected because emergency stop is active.
second_command = Message(
    sender="reasoning_agent",
    receiver="controller_agent",
    message_type=MessageType.COMMAND,
    payload={
        "command": "move_forward"
    },
    priority=1,
)

bus.publish(second_command)

time.sleep(0.5)


# Clear safety state.
bus.publish(clear_alert)

time.sleep(0.5)


# Command should now be accepted.
third_command = Message(
    sender="reasoning_agent",
    receiver="controller_agent",
    message_type=MessageType.COMMAND,
    payload={
        "command": "move_forward"
    },
    priority=1,
)

bus.publish(third_command)

time.sleep(0.5)

controller.stop()