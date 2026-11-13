import time

from agents.base_agent import BaseAgent
from communication.message_bus import MessageBus
from communication.schemas import Message, MessageType


class SenderAgent(BaseAgent):

    def process_message(self, message):
        print(
            f"[{self.name}] Received: {message.payload}"
        )


class ReceiverAgent(BaseAgent):

    def process_message(self, message):
        print(
            f"[{self.name}] Received: {message.payload}"
        )


bus = MessageBus()

sender = SenderAgent("sender")
receiver = ReceiverAgent("receiver")

bus.register(sender)
bus.register(receiver)

sender.start()
receiver.start()


message = Message(
    sender="sender",
    receiver="receiver",
    message_type=MessageType.COMMAND,
    payload={
        "command": "move_forward"
    }
)

sender.send(message)

time.sleep(1)

sender.stop()
receiver.stop()